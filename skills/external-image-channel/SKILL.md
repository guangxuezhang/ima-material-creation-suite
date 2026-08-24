---
name: external-image-channel
description: Directly generate or edit images through the user's configured external image API when the user says 外置通道生图、外置线路、外置生图通道, or asks to switch away from the built-in image generator. Run the request in the current task; never forward it to another thread.
---

# 外置生图通道

Use the bundled `scripts/external_image_channel.py` from the current task. Do not send prompts to “维度图生成器” or any other thread.

## Fixed configuration

- API base: `https://api2.laozhang.ai/v1/images`
- Model: `gpt-image-2-vip`
- Key source: environment variable `EXTERNAL_IMAGE_KEYS_FILE`, or `~/.codex/secrets/image_api_keys.txt` when unset.
- Never copy API keys into prompts, skill files, source control, commentary, or command output.
- Use `/generations` for new images and `/edits` when a local reference/edit target is supplied.

## Workflow

1. Inspect every reference image with the available image viewer.
2. Write the final prompt to a UTF-8 text file inside the current task's `work/` directory.
3. Choose a final output under the current task's `outputs/` directory unless the user names another destination.
4. Call the helper once per requested asset. For multiple assets, use different `--key-index` values and separate state files; concurrent calls are allowed.
5. Display or inspect each returned image and check the requested subject, composition, text, and size.
6. Report the saved files in the current task. Do not leave a deliverable in another task's output directory.

Example for a new image:

```powershell
python <skill-dir>\scripts\external_image_channel.py --prompt-file <prompt.txt> --output <image.png> --state-file <state.json> --key-index 0
```

Example using a reference image:

```powershell
python <skill-dir>\scripts\external_image_channel.py --prompt-file <prompt.txt> --reference <reference.png> --output <image.png> --state-file <state.json> --key-index 1
```

## Request safety and retries

- The helper writes `running` before sending and `succeeded`, `failed`, or `timeout_needs_confirmation` afterward.
- Never automatically retry `running`, `succeeded`, or `timeout_needs_confirmation`; doing so may duplicate charges.
- After `failed`, inspect the saved error. Submit again only when the user has requested a retry or the failure occurred before the API received the request.
- One requested image equals one API request. Do not silently create variants.
- Use a request timeout up to 600 seconds. Treat a timeout as indeterminate, not as proof that no image was created.
