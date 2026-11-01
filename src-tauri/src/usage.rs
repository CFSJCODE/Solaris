//! Métricas de uso dos provedores de chat (tokens, mensagens e custo).
//!
//! Cada resposta concluída grava um evento em `usage_events`. O resumo é
//! calculado sob demanda em três janelas:
//! - **Sessão atual**: janela deslizante que começa na primeira mensagem após a
//!   sessão anterior expirar e dura `session_hours`.
//! - **Esta semana**: do último reinício semanal (dia/hora local configurados)
//!   até o próximo.
//! - **Por modelo**: consumo semanal de cada modelo, com limite opcional
//!   expresso como fração do limite semanal.
//!
//! Os limites são orçamentos definidos pelo usuário, não cotas dos provedores.
use rusqlite::{params, Connection, Result};
use serde::{Deserialize, Serialize};

use crate::db::DbState;

const DAY: i64 = 86_400;
const WEEK: i64 = 7 * DAY;

pub fn migrate(conn: &Connection) -> Result<()> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS usage_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at      INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
            conversation_id INTEGER,
            provider        TEXT    NOT NULL,
            model           TEXT    NOT NULL,
            input_tokens    INTEGER NOT NULL DEFAULT 0,
            output_tokens   INTEGER NOT NULL DEFAULT 0,
            cost_usd        REAL
        );
        CREATE INDEX IF NOT EXISTS usage_events_time ON usage_events(created_at);
        CREATE TABLE IF NOT EXISTS usage_settings (
            id   INTEGER PRIMARY KEY CHECK (id = 1),
            json TEXT    NOT NULL
        );
        ",
    )
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ModelLimit {
    pub model: String,
    /// Fração do limite semanal reservada a este modelo (1–100).
    pub share_pct: u8,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct UsageLimits {
    pub session_hours: u32,
    pub session_tokens: u64,
    pub weekly_tokens: u64,
    /// Orçamento semanal opcional em USD.
    pub weekly_budget_usd: Option<f64>,
    /// 0 = domingo … 6 = sábado (horário local).
    pub reset_weekday: u8,
    pub reset_hour: u8,
    pub models: Vec<ModelLimit>,
}

impl Default for UsageLimits {
    fn default() -> Self {
        Self {
            session_hours: 5,
            session_tokens: 200_000,
            weekly_tokens: 2_000_000,
            weekly_budget_usd: None,
            reset_weekday: 6,
            reset_hour: 12,
            models: vec![ModelLimit {
                model: "claude-sonnet-5-5".into(),
                share_pct: 50,
            }],
        }
    }
}

impl UsageLimits {
    pub fn validate(&self) -> std::result::Result<(), String> {
        if !(1..=24).contains(&self.session_hours) {
            return Err("A sessão deve durar entre 1 e 24 horas.".into());
        }
        if self.session_tokens == 0 || self.weekly_tokens == 0 {
            return Err("Os limites de tokens devem ser maiores que zero.".into());
        }
        if self.session_tokens > 1_000_000_000 || self.weekly_tokens > 10_000_000_000 {
            return Err("Limite de tokens muito alto.".into());
        }
        if let Some(b) = self.weekly_budget_usd {
            if !b.is_finite() || b <= 0.0 {
                return Err("O orçamento semanal deve ser maior que zero.".into());
            }
        }
        if self.reset_weekday > 6 || self.reset_hour > 23 {
            return Err("Dia ou hora de reinício inválidos.".into());
        }
        if self.models.len() > 32 {
            return Err("Configure até 32 limites por modelo.".into());
        }
        let mut seen = std::collections::HashSet::new();
        for m in &self.models {
            let name = m.model.trim();
            if name.is_empty() || name.len() > 200 {
                return Err("Nome de modelo inválido.".into());
            }
            if !(1..=100).contains(&m.share_pct) {
                return Err(format!("O limite de {name} deve ficar entre 1% e 100%."));
            }
            if !seen.insert(name.to_string()) {
                return Err(format!("O modelo {name} aparece mais de uma vez."));
            }
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct UsageEvent {
    pub ts: i64,
    pub provider: String,
    pub model: String,
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub cost_usd: Option<f64>,
}

impl UsageEvent {
    fn tokens(&self) -> u64 {
        self.input_tokens + self.output_tokens
    }
}

#[derive(Debug, Clone, Default, Serialize, PartialEq)]
pub struct Totals {
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub tokens: u64,
    pub messages: u64,
    pub cost_usd: f64,
    /// Falso quando ao menos uma resposta não tinha preço conhecido.
    pub cost_complete: bool,
}

impl Totals {
    fn add(&mut self, e: &UsageEvent) {
        if self.messages == 0 {
            self.cost_complete = true;
        }
        self.input_tokens += e.input_tokens;
        self.output_tokens += e.output_tokens;
        self.tokens += e.tokens();
        self.messages += 1;
        match e.cost_usd {
            Some(c) => self.cost_usd += c,
            None => self.cost_complete = false,
        }
    }
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct UsageWindow {
    #[serde(flatten)]
    pub totals: Totals,
    pub limit_tokens: u64,
    pub percent: f64,
    /// Início da janela (Unix, segundos). Nulo se não há sessão ativa.
    pub started_at: Option<i64>,
    /// Próximo reinício (Unix, segundos). Nulo se não há sessão ativa.
    pub resets_at: Option<i64>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct ModelUsage {
    pub model: String,
    pub provider: Option<String>,
    #[serde(flatten)]
    pub totals: Totals,
    pub share_pct: Option<u8>,
    pub limit_tokens: u64,
    pub percent: f64,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Budget {
    pub spent_usd: f64,
    pub limit_usd: f64,
    pub percent: f64,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct UsageSummary {
    pub now: i64,
    pub session: UsageWindow,
    pub week: UsageWindow,
    pub budget: Option<Budget>,
    pub models: Vec<ModelUsage>,
    pub limits: UsageLimits,
}

fn percent(used: f64, limit: f64) -> f64 {
    if limit <= 0.0 {
        return 0.0;
    }
    ((used / limit) * 1000.0).round() / 10.0
}

/// Início da semana corrente em UTC, dado o deslocamento local (minutos a
/// leste de UTC, ex.: −180 para Brasília).
pub fn week_start(now: i64, tz_offset_min: i32, weekday: u8, hour: u8) -> i64 {
    let offset = i64::from(tz_offset_min) * 60;
    let local = now + offset;
    let days = local.div_euclid(DAY);
    // 01/01/1970 foi quinta-feira (4).
    let today = (days + 4).rem_euclid(7);
    let back = (today - i64::from(weekday)).rem_euclid(7);
    let mut boundary = (days - back) * DAY + i64::from(hour) * 3600;
    if boundary > local {
        boundary -= WEEK;
    }
    boundary - offset
}

/// Calcula o resumo. `events` deve estar em ordem cronológica e cobrir ao
/// menos os últimos oito dias.
pub fn summarize(
    events: &[UsageEvent],
    limits: &UsageLimits,
    now: i64,
    tz_offset_min: i32,
) -> UsageSummary {
    let span = i64::from(limits.session_hours) * 3600;

    // Sessão: cada uma começa na primeira mensagem após a anterior expirar.
    let mut session_start: Option<i64> = None;
    for e in events.iter().filter(|e| e.ts <= now) {
        if session_start.map_or(true, |s| e.ts >= s + span) {
            session_start = Some(e.ts);
        }
    }
    let session_start = session_start.filter(|s| now < s + span);
    let mut session_totals = Totals::default();
    if let Some(start) = session_start {
        for e in events.iter().filter(|e| e.ts >= start && e.ts <= now) {
            session_totals.add(e);
        }
    }
    let session = UsageWindow {
        percent: percent(session_totals.tokens as f64, limits.session_tokens as f64),
        totals: session_totals,
        limit_tokens: limits.session_tokens,
        started_at: session_start,
        resets_at: session_start.map(|s| s + span),
    };

    // Semana.
    let ws = week_start(now, tz_offset_min, limits.reset_weekday, limits.reset_hour);
    let weekly: Vec<&UsageEvent> = events
        .iter()
        .filter(|e| e.ts >= ws && e.ts <= now)
        .collect();
    let mut week_totals = Totals::default();
    for e in &weekly {
        week_totals.add(e);
    }
    let budget = limits.weekly_budget_usd.map(|limit| Budget {
        spent_usd: week_totals.cost_usd,
        limit_usd: limit,
        percent: percent(week_totals.cost_usd, limit),
    });
    let week = UsageWindow {
        percent: percent(week_totals.tokens as f64, limits.weekly_tokens as f64),
        totals: week_totals,
        limit_tokens: limits.weekly_tokens,
        started_at: Some(ws),
        resets_at: Some(ws + WEEK),
    };

    // Por modelo: primeiro os configurados (na ordem definida), depois os
    // demais usados nesta semana, do maior consumo para o menor.
    let mut models: Vec<ModelUsage> = limits
        .models
        .iter()
        .map(|m| ModelUsage {
            model: m.model.trim().to_string(),
            provider: None,
            totals: Totals::default(),
            share_pct: Some(m.share_pct),
            limit_tokens: limits.weekly_tokens * u64::from(m.share_pct) / 100,
            percent: 0.0,
        })
        .collect();
    let configured = models.len();
    for e in &weekly {
        let idx = match models.iter().position(|m| m.model == e.model) {
            Some(i) => i,
            None => {
                models.push(ModelUsage {
                    model: e.model.clone(),
                    provider: None,
                    totals: Totals::default(),
                    share_pct: None,
                    limit_tokens: limits.weekly_tokens,
                    percent: 0.0,
                });
                models.len() - 1
            }
        };
        let m = &mut models[idx];
        m.provider = Some(e.provider.clone());
        m.totals.add(e);
    }
    for m in &mut models {
        m.percent = percent(m.totals.tokens as f64, m.limit_tokens as f64);
    }
    models[configured..].sort_by_key(|m| std::cmp::Reverse(m.totals.tokens));

    UsageSummary {
        now,
        session,
        week,
        budget,
        models,
        limits: limits.clone(),
    }
}

impl DbState {
    pub fn record_usage(
        &self,
        conversation_id: Option<i64>,
        provider: &str,
        model: &str,
        input_tokens: u64,
        output_tokens: u64,
        cost_usd: Option<f64>,
    ) -> Result<()> {
        let conn = self.0.lock().unwrap();
        conn.execute(
            "INSERT INTO usage_events(conversation_id,provider,model,input_tokens,output_tokens,cost_usd)
             VALUES (?1,?2,?3,?4,?5,?6)",
            params![
                conversation_id,
                provider,
                model,
                input_tokens as i64,
                output_tokens as i64,
                cost_usd.filter(|c| c.is_finite() && *c >= 0.0)
            ],
        )?;
        Ok(())
    }

    pub fn usage_limits(&self) -> Result<UsageLimits> {
        let conn = self.0.lock().unwrap();
        let stored: Option<String> = conn
            .query_row("SELECT json FROM usage_settings WHERE id=1", [], |r| {
                r.get(0)
            })
            .ok();
        Ok(stored
            .and_then(|s| serde_json::from_str::<UsageLimits>(&s).ok())
            .filter(|l| l.validate().is_ok())
            .unwrap_or_default())
    }

    pub fn save_usage_limits(&self, limits: &UsageLimits) -> std::result::Result<(), String> {
        limits.validate()?;
        let encoded = serde_json::to_string(limits).map_err(|e| e.to_string())?;
        let conn = self.0.lock().unwrap();
        conn.execute(
            "INSERT INTO usage_settings(id,json) VALUES (1,?1)
             ON CONFLICT(id) DO UPDATE SET json=excluded.json",
            [encoded],
        )
        .map_err(|e| e.to_string())?;
        Ok(())
    }

    pub fn usage_summary(&self, now: i64, tz_offset_min: i32) -> Result<UsageSummary> {
        let limits = self.usage_limits()?;
        let since = now - WEEK - DAY;
        let conn = self.0.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT created_at, provider, model, input_tokens, output_tokens, cost_usd
             FROM usage_events WHERE created_at >= ?1 ORDER BY created_at, id",
        )?;
        let events = stmt
            .query_map([since], |r| {
                Ok(UsageEvent {
                    ts: r.get(0)?,
                    provider: r.get(1)?,
                    model: r.get(2)?,
                    input_tokens: r.get::<_, i64>(3)?.max(0) as u64,
                    output_tokens: r.get::<_, i64>(4)?.max(0) as u64,
                    cost_usd: r.get(5)?,
                })
            })?
            .collect::<Result<Vec<_>>>()?;
        Ok(summarize(&events, &limits, now, tz_offset_min))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    fn ev(ts: i64, model: &str, tokens: u64, cost: Option<f64>) -> UsageEvent {
        UsageEvent {
            ts,
            provider: "anthropic".into(),
            model: model.into(),
            input_tokens: tokens / 2,
            output_tokens: tokens - tokens / 2,
            cost_usd: cost,
        }
    }

    // Sábado, 31/10/2026 12:00 em Brasília (UTC−3) = 15:00 UTC.
    const SAT_NOON_BRT: i64 = 1_793_458_800;

    #[test]
    fn week_starts_on_configured_local_weekday_and_hour() {
        let brt = -180;
        // Exatamente no reinício: a semana começa agora.
        assert_eq!(week_start(SAT_NOON_BRT, brt, 6, 12), SAT_NOON_BRT);
        // Um minuto antes: a semana começou sete dias atrás.
        assert_eq!(
            week_start(SAT_NOON_BRT - 60, brt, 6, 12),
            SAT_NOON_BRT - WEEK
        );
        // Domingo seguinte: ainda é a semana iniciada no sábado.
        assert_eq!(week_start(SAT_NOON_BRT + DAY, brt, 6, 12), SAT_NOON_BRT);
        // Em UTC o mesmo instante é 15:00, já após o meio-dia.
        assert_eq!(week_start(SAT_NOON_BRT, 0, 6, 12), SAT_NOON_BRT - 3 * 3600);
    }

    #[test]
    fn session_rolls_over_after_window_expires() {
        let limits = UsageLimits::default(); // 5 h, 200k
        let t0 = SAT_NOON_BRT + 3600;
        let events = vec![
            ev(t0, "claude-haiku-5-5", 50_000, Some(0.01)),
            ev(t0 + 3600, "claude-haiku-5-5", 50_000, Some(0.01)),
            // Após 5 h: nova sessão.
            ev(t0 + 6 * 3600, "claude-haiku-5-5", 20_000, Some(0.01)),
        ];
        let s = summarize(&events, &limits, t0 + 2 * 3600, -180);
        assert_eq!(s.session.totals.tokens, 100_000);
        assert_eq!(s.session.percent, 50.0);
        assert_eq!(s.session.resets_at, Some(t0 + 5 * 3600));

        let s = summarize(&events, &limits, t0 + 5 * 3600 + 60, -180);
        assert_eq!(
            s.session.totals.tokens, 0,
            "sessão expirada e sem nova mensagem"
        );
        assert_eq!(s.session.resets_at, None);

        let s = summarize(&events, &limits, t0 + 7 * 3600, -180);
        assert_eq!(s.session.totals.tokens, 20_000);
        assert_eq!(s.session.started_at, Some(t0 + 6 * 3600));
        assert_eq!(s.week.totals.tokens, 120_000);
        assert_eq!(s.week.percent, 6.0);
    }

    #[test]
    fn weekly_reset_excludes_previous_week_and_models_use_share() {
        let limits = UsageLimits::default(); // sonnet = 50% de 2M
        let events = vec![
            ev(SAT_NOON_BRT - 60, "claude-sonnet-5-5", 900_000, Some(5.0)),
            ev(SAT_NOON_BRT + 60, "claude-sonnet-5-5", 250_000, Some(1.5)),
            ev(
                SAT_NOON_BRT + 120,
                "google/gemma-4-31b-it:free",
                40_000,
                Some(0.0),
            ),
            ev(SAT_NOON_BRT + 180, "x/sem-preco", 10_000, None),
        ];
        let s = summarize(&events, &limits, SAT_NOON_BRT + 3600, -180);
        assert_eq!(s.week.totals.tokens, 300_000);
        assert_eq!(s.week.resets_at, Some(SAT_NOON_BRT + WEEK));
        assert!(!s.week.totals.cost_complete);
        assert!((s.week.totals.cost_usd - 1.5).abs() < 1e-9);

        assert_eq!(s.models[0].model, "claude-sonnet-5-5");
        assert_eq!(s.models[0].limit_tokens, 1_000_000);
        assert_eq!(s.models[0].percent, 25.0);
        assert_eq!(s.models[1].model, "google/gemma-4-31b-it:free");
        assert_eq!(s.models[1].share_pct, None);
        assert_eq!(s.models[1].percent, 2.0);
        assert!(s.models[1].totals.cost_complete);
        assert_eq!(s.models[2].model, "x/sem-preco");
        assert!(!s.models[2].totals.cost_complete);
    }

    #[test]
    fn configured_model_without_usage_reports_zero() {
        let s = summarize(&[], &UsageLimits::default(), SAT_NOON_BRT, -180);
        assert_eq!(s.models.len(), 1);
        assert_eq!(s.models[0].percent, 0.0);
        assert_eq!(s.session.started_at, None);
        assert!(s.budget.is_none());
    }

    #[test]
    fn limits_are_validated_and_persisted() {
        let conn = Connection::open_in_memory().unwrap();
        migrate(&conn).unwrap();
        migrate(&conn).unwrap();
        let db = DbState(Mutex::new(conn));
        assert_eq!(db.usage_limits().unwrap(), UsageLimits::default());

        let mut bad = UsageLimits::default();
        bad.models[0].share_pct = 0;
        assert!(db.save_usage_limits(&bad).is_err());
        bad.models[0].share_pct = 30;
        bad.models.push(bad.models[0].clone());
        assert!(db.save_usage_limits(&bad).is_err());

        let mut good = UsageLimits::default();
        good.weekly_budget_usd = Some(10.0);
        good.session_hours = 4;
        db.save_usage_limits(&good).unwrap();
        assert_eq!(db.usage_limits().unwrap(), good);

        db.record_usage(
            Some(1),
            "anthropic",
            "claude-sonnet-5-5",
            1000,
            500,
            Some(2.5),
        )
        .unwrap();
        let now: i64 =
            db.0.lock()
                .unwrap()
                .query_row("SELECT CAST(strftime('%s','now') AS INTEGER)", [], |r| {
                    r.get(0)
                })
                .unwrap();
        let s = db.usage_summary(now, -180).unwrap();
        assert_eq!(s.session.totals.tokens, 1500);
        assert_eq!(s.budget.unwrap().percent, 25.0);
    }
}
