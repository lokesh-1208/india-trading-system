// Zerodha pieces shared by the Settings page (setup) and the Intraday page (account view).
import { FormEvent, useCallback, useEffect, useState } from "react";
import { getJson, postJson, UseApi, ZAccount, ZStatus } from "../api";
import { Empty, Loading, Tag } from "./ui";
import { price, rupees, signedRupees } from "../format";

const tone = (value: number) => (value >= 0 ? "up" : "down");

/** Everything needed to connect: keys, the redirect address, the daily login, a test, and removal. */
export function ZerodhaSetup({ status }: { status: UseApi<ZStatus> }) {
  const [keys, setKeys] = useState({ api_key: "", api_secret: "" });
  const [editing, setEditing] = useState(false);
  const [copied, setCopied] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState<{ tone: string; text: string } | null>(null);
  const landed = new URLSearchParams(window.location.search).get("zerodha");
  const st = status.data;
  if (!st) return <Loading height={80} />;

  const fail = (error: Error) => setMessage({ tone: "down", text: error.message });
  const saveKeys = (event: FormEvent) => {
    event.preventDefault();
    postJson<ZStatus>("/api/zerodha/keys", keys)
      .then((found) => { status.setData(found); setEditing(false); setKeys({ api_key: "", api_secret: "" });
        setMessage({ tone: "up", text: "Keys saved on this computer. Now click Connect Zerodha." }); }).catch(fail);
  };
  const test = () => {
    setMessage({ tone: "warn", text: "Testing…" });
    getJson<ZAccount>("/api/zerodha/account")
      .then((found) => setMessage({ tone: "up", text: `Connection works. ${rupees(found.funds.available)} available, ${found.positions.length} position(s) today.` }))
      .catch((error: Error) => { setMessage({ tone: "down", text: error.message }); status.reload(); });
  };
  const disconnect = () => postJson<ZStatus>("/api/zerodha/disconnect", {}).then((found) => { status.setData(found); setMessage(null); }).catch(fail);
  const removeKeys = () => {
    if (!confirming) { setConfirming(true); return; }
    setConfirming(false);
    postJson<ZStatus>("/api/zerodha/forget-keys", {}).then((found) => { status.setData(found); setMessage({ tone: "up", text: "Keys removed from this computer." }); }).catch(fail);
  };

  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="record-row">
        <span className="grow">
          {st.connected ? <Tag tone="up">Connected today</Tag> : st.configured ? <Tag tone="warn">Keys saved, not logged in today</Tag> : <Tag tone="plain">Not set up</Tag>}
          {" "}<span className="small muted">{st.connected ? `as ${st.user}` : st.configured ? `API key ${st.key_hint}` : ""}</span>
        </span>
      </div>
      {landed === "connected" && st.connected ? <div className="notice up" role="status">Connected to Zerodha for today.</div> : null}
      {landed === "failed" && !st.connected ? <div className="notice down" role="alert">The Zerodha login did not complete. Click Connect Zerodha and try again.</div> : null}
      {message ? <div className={`notice ${message.tone}`} role="status">{message.text}</div> : null}

      <div className="notice" style={{ background: "var(--blue-bg)" }}>
        <strong>How the connection works.</strong> Zerodha has two "callback" addresses. The <strong>redirect URL</strong> is where Zerodha sends your browser
        after you log in; Kasauti handles it for you at the address below, so the daily login completes on its own. The <strong>postback (webhook) URL</strong>
        pushes order updates to a public https address; Zerodha does not offer it on the free Personal plan, so leave it empty. Kasauti reads your orders
        and positions again every minute instead. Your Zerodha password is never seen by Kasauti.
      </div>

      {!st.configured || editing ? (
        <form className="stack" style={{ gap: 12 }} onSubmit={saveKeys} aria-label="Zerodha API keys">
          <ol className="small" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>
            <li>Open developers.kite.trade, sign in with your Zerodha ID, and create a new app on the free <strong>Personal</strong> plan.</li>
            <li>Redirect URL: paste exactly <code>{st.redirect_url}</code>{" "}
              <button type="button" className="small" onClick={() => { navigator.clipboard?.writeText(st.redirect_url); setCopied(true); }}>{copied ? "Copied" : "Copy"}</button></li>
            <li>Postback URL: leave empty.</li>
            <li>Copy the app's <strong>API key</strong> and <strong>API secret</strong> into the boxes below. They are saved only on this computer.</li>
          </ol>
          <div className="record-row">
            <label className="grow">API key<input required value={keys.api_key} autoComplete="off" onChange={(event) => setKeys({ ...keys, api_key: event.target.value })} /></label>
            <label className="grow">API secret<input required type="password" value={keys.api_secret} autoComplete="off" onChange={(event) => setKeys({ ...keys, api_secret: event.target.value })} /></label>
            <button className="primary" type="submit">Save keys</button>
            {editing ? <button type="button" onClick={() => setEditing(false)}>Cancel</button> : null}
          </div>
        </form>
      ) : (
        <div className="record-row">
          <span className="small grow">
            {st.connected ? "Zerodha ends your login every morning, so connect again tomorrow." : "Zerodha ends your login every morning. Connect once each day before you use the Intraday tab."}
          </span>
          {st.connected ? (
            <>
              <button type="button" className="primary" onClick={test}>Test connection</button>
              <button type="button" onClick={disconnect}>Disconnect</button>
            </>
          ) : (
            <a href={st.login_url ?? "#"}><button type="button" className="primary">Connect Zerodha</button></a>
          )}
          <button type="button" className="small" onClick={() => setEditing(true)}>Change keys</button>
          <button type="button" className={`small${confirming ? " danger" : ""}`} onClick={removeKeys} onBlur={() => setConfirming(false)}>
            {confirming ? "Sure? Remove keys" : "Remove keys"}</button>
        </div>
      )}
    </div>
  );
}

/** Funds, today's positions and orders. Reads again every minute while shown. */
export function ZerodhaAccount() {
  const [account, setAccount] = useState<ZAccount | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const load = useCallback(() => {
    getJson<ZAccount>("/api/zerodha/account").then((found) => { setAccount(found); setProblem(null); })
      .catch((error: Error) => setProblem(error.message));
  }, []);
  useEffect(() => { load(); const timer = setInterval(load, 60000); return () => clearInterval(timer); }, [load]);

  if (problem) return <div className="notice down" role="alert">{problem} <button type="button" className="small" onClick={load}>Try again</button></div>;
  if (!account) return <Loading height={80} />;
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="grid-tiles">
        <div className="tile"><span className="name">Available to trade</span><span className="value num">{rupees(account.funds.available)}</span></div>
        <div className="tile"><span className="name">Used</span><span className="value num">{rupees(account.funds.used)}</span></div>
        <div className="tile"><span className="name">Today's P&L (Zerodha, before charges)</span>
          <span className={`value num ${tone(account.pnl)}`}>{signedRupees(account.pnl)}</span></div>
      </div>
      {account.positions.length ? (
        <div className="table-wrap"><table>
          <thead><tr><th>Position</th><th>Product</th><th className="right">Qty</th><th className="right">Average</th><th className="right">Last</th><th className="right">P&L</th></tr></thead>
          <tbody>{account.positions.map((p) => (
            <tr key={p.symbol + p.product}><td><strong>{p.symbol}</strong></td><td>{p.product}</td><td className="right num">{p.qty}</td>
              <td className="right num">{price(p.average)}</td><td className="right num">{price(p.last)}</td>
              <td className={`right num ${tone(p.pnl)}`}>{signedRupees(p.pnl)}</td></tr>))}</tbody>
        </table></div>
      ) : <Empty>No positions today.</Empty>}
      {account.orders.length ? (
        <details><summary className="small">Today's orders ({account.orders.length})</summary>
          <div className="table-wrap"><table>
            <thead><tr><th>Time</th><th>Stock</th><th>Side</th><th className="right">Filled</th><th>Type</th><th className="right">Price</th><th className="right">Trigger</th><th>Status</th></tr></thead>
            <tbody>{account.orders.map((o, index) => (
              <tr key={index}><td className="small">{o.time}</td><td>{o.symbol}</td><td>{o.side}</td>
                <td className="right num">{o.filled}/{o.qty}</td><td>{o.type}</td>
                <td className="right num">{o.price ? price(o.price) : "–"}</td><td className="right num">{o.trigger ? price(o.trigger) : "–"}</td><td>{o.status}</td></tr>))}</tbody>
          </table></div></details>
      ) : null}
    </div>
  );
}
