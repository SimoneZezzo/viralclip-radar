# Static demo

Build the React app with `VITE_STATIC_DATA=1`, then publish the rankings into the same build directory. From the repository root in PowerShell:

```powershell
$env:VITE_STATIC_DATA = '1'
npm --prefix web run build -- --outDir static/dist
Remove-Item Env:VITE_STATIC_DATA
uv run --offline --no-sync python -m viralclip.publish --registry PATH_TO_REGISTRY --output web/static/dist --game "1867279146=GTA VI" --game "32982=GTA V"
```

On Linux, prefix the build command with `VITE_STATIC_DATA=1`. Serve the contents of `web/static/dist/` at the root or a subdirectory of a static host. The default build in `web/dist/` uses FastAPI.

To refresh rankings, rerun the publish command. Supply every game to include. The first game opens by default. Each game file gets a new content-hashed name (`ID-HASH.json`) listed in `index.json`, so an update never rewrites a file the live index references. The publisher writes the new game files, replaces the index last, keeps the previous generation and any game file younger than six hours for readers or caches still holding an older index, and removes older game files. If a game file is gone, the front end reloads the index once. An interrupted run leaves the previous index and its files intact. A host with release-based deployments can switch the whole built directory at once.

If a publisher is killed during staging, it can leave `rankings/.publishing/` in the build directory. Once the publisher has stopped, remove that staging directory and rerun the command.
