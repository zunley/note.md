import { useState } from "react";
import { api, saveAuth } from "./api";

export function Login({ onDone }: { onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setErr("");
    try {
      const r = await api.login(password);
      saveAuth({ token: r.token, exp: r.expires_at });
      onDone();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "登录失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={submit}>
        <h1>note.md</h1>
        <div className="sub">输入登录口令进入笔记本</div>
        <input
          type="password"
          autoFocus
          placeholder="登录口令"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button className="nb-btn solid" disabled={busy}>
          {busy ? "登录中…" : "进入"}
        </button>
        <div className="err">{err}</div>
      </form>
    </div>
  );
}
