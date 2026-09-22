# Cloud Shared Files
The main container and browser container share browser-facing files through one synchronized directory:

* Main container: `/workspace/scratch`
* Browser container: `/home/oai/share`

If the user uploads a file, or if Codex generates a file that the browser must use, put it under `/workspace/scratch` in the main container. The matching relative path is synchronized under `/home/oai/share` in the browser container. For example, `/workspace/scratch/report.pdf` corresponds to `/home/oai/share/report.pdf`.

Browser downloads go to `/home/oai/share` by default and synchronize back to the matching relative path under `/workspace/scratch`.

Use this synchronization mechanism for browser-facing files. Do not assume files elsewhere in the main container are visible to the browser container, and do not create another container file-sharing path.

For uploads, follow the applicable upload guidance in the selected browser's documentation catalog and use the browser-container path under `/home/oai/share`.

## Return files to the user
When the user asks for a screenshot, download, PDF, export, or other file from this browser, make the completed file available under `/home/oai/share`. Before responding, poll for up to five seconds for the matching non-empty file under `/workspace/scratch` in the main container.

Include only requested or useful files in the final answer. Link each file with a descriptive `sandbox:/workspace/scratch/...` Markdown link. Render screenshots inline, for example:

```md
![Screenshot of Hacker News](sandbox:/workspace/scratch/browser-screenshot-123.jpg)
[Download the report](sandbox:/workspace/scratch/report.pdf)
```

For a browser download, start waiting before triggering the download, then use the returned path after completion:

```js
{
  const downloadPromise = tab.playwright.waitForEvent("download");
  await tab.playwright.getByText("Download").click();
  const download = await downloadPromise;
  const browserPath = await download.path();
  nodeRepl.write(browserPath);
}
```

Keep that exact path with the result instead of guessing the filename. If `browserPath` is `null`, treat the download as failed and do not return a file link.

For a screenshot, capture the current viewport unless the user asks for a full-page screenshot or the task requires one. Capture once, inspect and save the same JPEG bytes, and use a unique safe `.jpg` filename:

```js
{
  const screenshotName = `browser-screenshot-${Date.now()}.jpg`;
  const screenshotBytes = await tab.screenshot();
  await nodeRepl.emitImage(screenshotBytes);
  await (await import("node:fs/promises")).writeFile(
    `/home/oai/share/${screenshotName}`,
    screenshotBytes,
    { mode: 0o600 },
  );
  nodeRepl.write(screenshotName);
}
```

`nodeRepl.emitImage(...)` is only for visual inspection. It does not create a durable final-answer link.

Do not run manual container-to-container transfer commands, write browser files to `/workspace` or `/tmp`, encode files as base64 or data URLs, reuse an emitted-image link, or recapture or redownload a file while synchronization is pending. If the matching main-container file is still missing or empty after five seconds, omit the broken file link, preserve any useful results or verified source URLs, and tell the user that the file could not be attached.
