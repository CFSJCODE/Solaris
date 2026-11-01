import React from "react"
import ReactDOM from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import App from "./App"
import "./styles/solaris.css"
import "./styles/liquid/tokens.css"
import "./styles/liquid/materials.css"
import "./styles/liquid/components.css"
import { MaterialProvider } from "./design/MaterialProvider"
import { GlassBackdrop } from "./design/GlassBackdrop"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60,
      retry: 1,
    },
  },
})

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <MaterialProvider>
        <GlassBackdrop>
          <App />
        </GlassBackdrop>
      </MaterialProvider>
    </QueryClientProvider>
  </React.StrictMode>,
)
