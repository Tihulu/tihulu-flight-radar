"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const root=path.resolve(__dirname,"..");
const read=file=>fs.readFileSync(path.join(root,file),"utf8");
const readme=read("README.md");
const install=read("tihulu_flight_radar/web/install.html");
const index=read("tihulu_flight_radar/web/index.html");
const pages=read(".github/workflows/pages.yml");
const installer=read("scripts/install-linux.sh");
const switcher=read("scripts/popos-version-switch.sh");
test("main README and website show one-line installer using canonical main",()=>{
 const url="https://raw.githubusercontent.com/Tihulu/tihulu-flight-radar/main/scripts/install-linux.sh";
 assert.ok(readme.includes(url));
 assert.ok(install.includes(url));
 assert.match(readme,/set -o pipefail/);
 assert.match(install,/set -o pipefail/);
 assert.match(index,/href="\.\/install\.html"/);
 assert.match(readme,/https:\/\/tihulu\.github\.io\/tihulu-flight-radar\//);
 assert.match(readme,/https:\/\/tihulu\.github\.io\/TIHULU-TEXT-CENTER\/flight_radar\//);
 assert.match(readme,/0\.3\.2\.dev4/);
 assert.match(install,/<title>Install · TIHULU Flight Radar<\/title>/);
});
test("single-install path never purges readsb or retunes USB",()=>{
 assert.match(installer,/ref="\$\{TIHULU_REF:-main\}"/);
 assert.match(installer,/pipx install --force/);
 assert.doesNotMatch(installer,/apt-get purge|systemctl restart readsb/);
 assert.match(readme,/readsb/);
 assert.match(readme,/not WebUSB/);
});
test("0.3.1 pinned rollback is accessible without changing main",()=>{
 assert.match(switcher,/67280cd84feb89faec6a80f5fe2a55ce5f7b89e6/);
 assert.match(switcher,/expected="0\.3\.1"/);
 assert.match(switcher,/expected="0\.3\.2\.dev4"/);
 assert.match(readme,/main\/scripts\/popos-version-switch\.sh/);
 assert.match(install,/main\/scripts\/popos-version-switch\.sh/);
 assert.match(readme,/legacy\/v0\.3\.1/);
});
test("Main is canonical Pages source after merge",()=>{
 assert.match(pages,/branches:\s*\[main/);
 assert.match(pages,/github\.ref == 'refs\/heads\/main'/);
 assert.match(pages,/tests\/release_main\.test\.cjs/);
});
