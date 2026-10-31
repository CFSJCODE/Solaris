import { useState, useRef, useCallback, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";

interface Detection {
  label: string;
  conf: number;
  box_coords: number[];
}

interface VisionFrame {
  jpeg_b64: string;
  detections: Detection[];
}

const CONF_DEFAULT = 0.35;
const INTERVAL_MS = 800;

export default function VisionPage() {
  const [running, setRunning] = useState(false);
  const [frame, setFrame] = useState<VisionFrame | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [conf, setConf] = useState(CONF_DEFAULT);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const busyRef = useRef(false);

  const capture = useCallback(async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    try {
      const result = await invoke<VisionFrame>("vision_frame", { source: 0, conf });
      setFrame(result);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      busyRef.current = false;
    }
  }, [conf]);

  const start = useCallback(() => {
    setRunning(true);
    capture();
    intervalRef.current = setInterval(capture, INTERVAL_MS);
  }, [capture]);

  const stop = useCallback(() => {
    setRunning(false);
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  // Restart interval when conf changes while running
  useEffect(() => {
    if (running) {
      stop();
      start();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conf]);

  return (
    <div className="vision-page">
      <h2 className="vision-title">Visão Computacional</h2>
      <p className="vision-subtitle">YOLOv8n · COCO 80 classes · CPU-only</p>

      <div className="vision-controls">
        <label className="vision-conf-label">
          Confiança mínima: <strong>{Math.round(conf * 100)}%</strong>
          <input
            type="range"
            min={0.1}
            max={0.9}
            step={0.05}
            value={conf}
            onChange={e => setConf(parseFloat(e.target.value))}
            className="vision-slider"
          />
        </label>

        {running ? (
          <button className="btn-danger" onClick={stop}>
            Parar câmera
          </button>
        ) : (
          <button className="btn-primary" onClick={start}>
            Iniciar câmera
          </button>
        )}
      </div>

      {error && <p className="vision-error">{error}</p>}

      {frame && (
        <div className="vision-content">
          <div className="vision-frame-wrap">
            <img
              src={`data:image/jpeg;base64,${frame.jpeg_b64}`}
              alt="frame anotado"
              className="vision-frame-img"
            />
            {running && <span className="vision-live-badge">● AO VIVO</span>}
          </div>

          <div className="vision-detections">
            <h3 className="vision-det-title">
              Detecções ({frame.detections.length})
            </h3>
            {frame.detections.length === 0 ? (
              <p className="vision-det-empty">Nenhum objeto detectado.</p>
            ) : (
              <ul className="vision-det-list">
                {frame.detections.map((d, i) => (
                  <li key={i} className="vision-det-item">
                    <span className="vision-det-label">{d.label}</span>
                    <span className="vision-det-conf">
                      {Math.round(d.conf * 100)}%
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {!frame && !error && (
        <div className="vision-empty">
          <span style={{ fontSize: 48, opacity: 0.2 }}>◉</span>
          <p>Clique em <strong>Iniciar câmera</strong> para começar.</p>
        </div>
      )}
    </div>
  );
}
