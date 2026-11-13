/** Target checks shared by k6 and the offline safety tests. */
export function configuration(env) {
  const raw = env.BASE_URL || "http://127.0.0.1:8000";
  const match = /^(https?):\/\/(\[::1\]|[a-zA-Z0-9.-]+)(?::([0-9]{1,5}))?\/?$/.exec(raw);
  if (!match || (match[3] && (+match[3] < 1 || +match[3] > 65535))) {
    throw new Error("BASE_URL must be an HTTP(S) origin without credentials, path, query or fragment.");
  }
  const base = raw.replace(/\/$/, "");
  const host = match[2].toLowerCase();
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(host);
  const profile = env.PROFILE || (local ? "local" : "public");
  if (!["local", "public"].includes(profile)) {
    throw new Error("PROFILE must be local or public.");
  }
  if (env.SPEECH && !["0", "1"].includes(env.SPEECH)) {
    throw new Error("SPEECH must be 0 or 1.");
  }
  const speech = env.SPEECH === "1";
  if (speech && env.CI && !["0", "false"].includes(env.CI.toLowerCase())) {
    throw new Error("Speech load is disabled in CI.");
  }
  if (speech && !local) {
    const namedStaging = /(^|[.-])stag(e|ing)([.-]|$)/.test(host);
    if (!namedStaging || match[1] !== "https" || env.STAGING_BASE_URL !== base) {
      throw new Error("Speech needs loopback or an HTTPS staging hostname explicitly matched by STAGING_BASE_URL.");
    }
  }
  return { base, local, profile, speech, desk: Boolean(env.DISPATCH_PASSCODE) };
}
