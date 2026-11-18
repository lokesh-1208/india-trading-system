// Settings: connect Kasauti to your Zerodha account.
import { useApi, ZStatus } from "../api";
import { Panel, Problem } from "../components/ui";
import { ZerodhaAccount, ZerodhaSetup } from "../components/Zerodha";

export default function SettingsPage() {
  const status = useApi<ZStatus>("/api/zerodha/status");
  return (
    <>
      <h1>Settings</h1>
      <p className="small muted" style={{ marginTop: -8 }}>Connect your Zerodha account. Kasauti only reads your funds, positions and orders; it never places an order.</p>
      <div className="stack">
        <Panel title="Zerodha connection" aside="Kite Connect Personal plan (free). It gives account data, not market prices.">
          {status.error ? <Problem error={status.error} retry={status.reload} /> : <ZerodhaSetup status={status} />}
        </Panel>
        {status.data?.connected ? (
          <Panel title="Your Zerodha account today" aside="Refreshes every minute">
            <ZerodhaAccount />
          </Panel>
        ) : null}
      </div>
    </>
  );
}
