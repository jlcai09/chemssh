# cclib

`cclib` is a chemssh example plugin. It parses quantum chemistry output files on the backend and sends structure-compatible trajectory data to the existing chemssh preview window.

## Frontend Assets

The plugin UI is bundled under `frontend/bundle/` and is shipped with the plugin. It does not need a separate frontend build step.

## Dependencies

The manifest defaults to `host` mode, which installs `cclib` into the same Python environment that runs chemssh:

```json
{
  "python": {
    "mode": "host",
    "requirements": "backend/requirements.txt"
  }
}
```

Use chemssh's plugin management API or the cclib plugin panel to install dependencies. The equivalent command is:

```powershell
.\.venv\Scripts\python -m pip install -r plugins\cclib\backend\requirements.txt
```

If dependencies are missing, the plugin can still load, but `probe` and structure parsing will report that `cclib` is unavailable. The plugin manager can also install to a plugin-local venv or validate an external Python interpreter for plugins that choose those modes.
