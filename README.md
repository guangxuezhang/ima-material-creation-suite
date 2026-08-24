# IMA Material Creation Suite

Private, portable package for the user's IMA-based content workflow.

## Included

- `ima-material-creation`: longform, marketing, and poster-marketing workflows.
- `external-image-channel`: external GPT image generation/editing with per-task state.
- Portable Feishu Bitable delivery helper.
- Windows installer and validation scripts.

## Install on another Windows device

1. Install/connect `ima-skill` in Codex and authorize the same IMA knowledge bases.
2. Run `powershell -ExecutionPolicy Bypass -File scripts/install.ps1`.
3. Edit `~/.codex/secrets/ima-material-creation.env`.
4. Put external image keys in the configured local key file, one key per line.
5. Grant the configured Feishu app access to the target Bitable.
6. Run `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`.
7. Run the same command with `-Live` to validate Feishu read access without writing a record.

## Update

Pull the latest private repository, rerun `scripts/install.ps1`, and then run `scripts/verify.ps1`. Existing local secrets are preserved.

Never commit real API keys, Feishu secrets, local `.env` files, generated images, or task state files.
