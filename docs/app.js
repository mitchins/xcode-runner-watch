"use strict";

const REPOSITORY = "mitchins/xcode-runner-watch";
const RAW_URL = `https://raw.githubusercontent.com/${REPOSITORY}/main/latest/macos-latest.json`;
const RUNS_URL = `https://api.github.com/repos/${REPOSITORY}/actions/runs?branch=main&per_page=50`;
const RELEASES_URL = `https://api.github.com/repos/${REPOSITORY}/releases?per_page=20`;

function byId(id) {
  return document.getElementById(id);
}

function make(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function setPageStatus(message, kind = "") {
  const status = byId("page-status");
  status.textContent = message;
  status.className = `page-status${kind ? ` is-${kind}` : ""}`;
}

function githubLink(url, label, className = "inline-link") {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  if (parsed.protocol !== "https:" || parsed.hostname !== "github.com") return null;
  const link = make("a", className, label);
  link.href = parsed.href;
  link.rel = "noopener noreferrer";
  return link;
}

async function fetchJson(url) {
  const response = await fetch(url, {
    cache: "no-store",
    headers: { Accept: "application/vnd.github+json" },
  });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json();
}

function formatDate(value) {
  if (!value) return "Date unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(date) + " UTC";
}

function renderFreshness(runs) {
  const priorLink = byId("last-check-link");
  priorLink.hidden = true;
  priorLink.removeAttribute("href");
  const scheduled = (runs.workflow_runs || [])
    .filter((run) => run.path === ".github/workflows/publish-macos-latest.yml"
      && run.head_branch === "main"
      && run.event === "schedule"
      && run.status === "completed"
      && run.conclusion === "success")
    .sort((a, b) => new Date(b.run_started_at || b.created_at) - new Date(a.run_started_at || a.created_at));
  const latest = scheduled[0];
  if (!latest) {
    byId("last-check-value").textContent = "No successful scheduled check found";
    byId("last-check-note").textContent = "This comes from the public Actions run history. The snapshot capture time is shown separately.";
    return;
  }
  byId("last-check-value").textContent = formatDate(latest.run_started_at || latest.created_at);
  byId("last-check-note").textContent = "Latest completed nightly run on main that finished successfully.";
  const link = githubLink(latest.html_url, "Open workflow run ↗");
  if (link) {
    const holder = byId("last-check-link");
    holder.href = link.href;
    holder.rel = link.rel;
    holder.textContent = link.textContent;
    holder.hidden = false;
  }
}

function renderToolchain(manifest) {
  const xcode = manifest.xcode?.xcodebuild_version || {};
  const swift = manifest.swift?.swift_version || {};
  const system = manifest.system || {};
  byId("runner-label").textContent = manifest.runner_label || "Runner label unavailable";
  byId("toolchain-cards").replaceChildren();

  const xcodeCard = make("article", "tool-card");
  xcodeCard.append(make("p", "card-label", "Xcode"));
  xcodeCard.append(make("p", "tool-version", xcode.xcode || "Version not reported"));
  xcodeCard.append(make("p", "tool-detail", xcode.build ? `Build ${xcode.build}` : "Build not reported"));

  const swiftCard = make("article", "tool-card");
  swiftCard.append(make("p", "card-label", "Swift"));
  swiftCard.append(make("p", "tool-version", swift.version || "Version not reported"));
  swiftCard.append(make("p", "tool-detail", swift.target || "Target not reported"));

  const macCard = make("article", "tool-card");
  macCard.append(make("p", "card-label", "macOS runner"));
  macCard.append(make("p", "tool-version", system.product_version || "Version not reported"));
  macCard.append(make("p", "tool-detail", system.build_version ? `Build ${system.build_version}` : "Build not reported"));
  byId("toolchain-cards").append(xcodeCard, swiftCard, macCard);
}

function sdkDetails(value) {
  if (typeof value === "string") return { version: value, build: null };
  if (value && typeof value === "object") return { version: value.version || null, build: value.build || null };
  return { version: null, build: null };
}

function renderSdks(manifest) {
  const entries = [
    ["iphoneos", "iOS device"],
    ["iphonesimulator", "iOS simulator"],
    ["macosx", "macOS"],
  ];
  const grid = byId("sdk-cards");
  grid.replaceChildren();
  for (const [key, label] of entries) {
    const sdk = sdkDetails(manifest.sdks?.[key]);
    const card = make("article", "sdk-card");
    card.append(make("p", "card-label", label));
    const line = make("div", "sdk-version-line");
    line.append(make("span", "sdk-version", sdk.version || "Version not reported"));
    line.append(make("span", "sdk-build", sdk.build ? `Build ${sdk.build}` : "Build not reported"));
    card.append(line);
    grid.append(card);
  }
}

function runtimeName(runtime) {
  if (!runtime || typeof runtime !== "object") return "Unknown runtime";
  if (runtime.name) return runtime.name;
  const identifier = runtime.identifier || "Unknown runtime";
  return identifier.split("SimRuntime.").pop().replaceAll("-", " ");
}

function renderRuntimes(manifest) {
  const runtimes = manifest.simulators?.runtimes?.runtimes;
  const list = byId("runtime-list");
  list.replaceChildren();
  if (!Array.isArray(runtimes)) {
    list.append(make("p", "empty-state", "Runtime information is missing from this snapshot."));
    byId("runtime-count").textContent = "Unavailable";
    return;
  }
  const sorted = runtimes.filter((runtime) => runtime && typeof runtime === "object")
    .sort((a, b) => runtimeName(a).localeCompare(runtimeName(b)));
  byId("runtime-count").textContent = `${sorted.length} ${sorted.length === 1 ? "runtime" : "runtimes"}`;
  if (sorted.length === 0) {
    list.append(make("p", "empty-state", "No simulator runtimes were reported in this snapshot."));
    return;
  }
  for (const runtime of sorted) {
    const card = make("article", "runtime-card");
    const details = make("div");
    details.append(make("p", "runtime-name", runtimeName(runtime)));
    details.append(make("p", "runtime-id", runtime.identifier || "Identifier not reported"));
    const version = runtime.version || "Version not reported";
    const build = runtime.buildversion || runtime.buildVersion;
    card.append(details, make("div", "runtime-version", build ? `${version} · ${build}` : version));
    const available = typeof runtime.isAvailable === "boolean"
      ? runtime.isAvailable
      : (typeof runtime.available === "boolean" ? runtime.available : null);
    const badge = make("span", `availability ${available === null ? "unknown" : (available ? "available" : "unavailable")}`,
      available === null ? "Availability not reported" : (available ? "Available" : "Unavailable"));
    card.append(make("span"), badge);
    list.append(card);
  }
}

function renderSnapshot(manifest) {
  renderToolchain(manifest);
  renderSdks(manifest);
  renderRuntimes(manifest);
  byId("snapshot-value").textContent = formatDate(manifest.observed_at);
}

function renderHistory(releases) {
  const list = byId("history-list");
  list.replaceChildren();
  const visible = (Array.isArray(releases) ? releases : [])
    .filter((release) => release && typeof release === "object")
    .filter((release) => !release.draft && !release.prerelease)
    .sort((a, b) => new Date(b.published_at || b.created_at) - new Date(a.published_at || a.created_at));
  if (!visible.length) {
    list.append(make("p", "empty-state", "No change releases yet. The first meaningful environment change will appear here."));
    return;
  }
  for (const release of visible.slice(0, 12)) {
    const card = make("article", "history-card");
    const topline = make("div", "history-topline");
    const title = githubLink(release.html_url, release.name || release.tag_name || "Runner environment changed", "history-title");
    topline.append(title || make("p", "history-title", release.name || "Runner environment changed"));
    topline.append(make("time", "history-date", formatDate(release.published_at || release.created_at)));
    card.append(topline);
    card.append(make("p", "history-notes", release.body || "Release notes were not provided."));
    const runUrlMatch = (release.body || "").match(/\[successful capture workflow run\]\((https:\/\/github\.com\/[^)]+)\)/);
    if (runUrlMatch) {
      const runLink = githubLink(runUrlMatch[1], "View capture run ↗", "history-run");
      if (runLink) card.append(runLink);
    }
    list.append(card);
  }
}

async function refresh() {
  const button = byId("refresh-button");
  button.disabled = true;
  setPageStatus("Loading the latest published snapshot and public GitHub history…");
  const [manifestResult, runsResult, releasesResult] = await Promise.allSettled([
    fetchJson(RAW_URL),
    fetchJson(RUNS_URL),
    fetchJson(RELEASES_URL),
  ]);

  const issues = [];
  if (manifestResult.status === "fulfilled") {
    renderSnapshot(manifestResult.value);
  } else {
    issues.push("The raw JSON snapshot could not be loaded.");
    byId("snapshot-value").textContent = "Snapshot unavailable";
    byId("runtime-count").textContent = "Unavailable";
    byId("toolchain-cards").replaceChildren(make("p", "empty-state", "Could not load Xcode and runner details. Try refreshing or open the raw JSON feed."));
    byId("sdk-cards").replaceChildren(make("p", "empty-state", "Could not load SDK details."));
    byId("runtime-list").replaceChildren(make("p", "empty-state", "Could not load simulator runtimes."));
  }
  if (runsResult.status === "fulfilled") {
    renderFreshness(runsResult.value);
  } else {
    issues.push("The latest successful scheduled check could not be verified.");
    byId("last-check-link").hidden = true;
    byId("last-check-value").textContent = "Check status unavailable";
    byId("last-check-note").textContent = "GitHub Actions history could not be loaded. Snapshot capture time is shown separately.";
  }
  if (releasesResult.status === "fulfilled") {
    renderHistory(releasesResult.value);
  } else {
    issues.push("Change history could not be loaded.");
    byId("history-list").replaceChildren(make("p", "empty-state", "GitHub release history could not be loaded. You can open all releases directly."));
  }
  if (issues.length) {
    setPageStatus(`${issues.join(" ")} Some page data may be unavailable; the raw feed and GitHub links remain available.`, "warning");
  } else {
    setPageStatus("Snapshot and history loaded. Snapshot capture time and latest successful nightly check are shown separately.");
  }
  button.disabled = false;
}

byId("refresh-button").addEventListener("click", refresh);
refresh();
