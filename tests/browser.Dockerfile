ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY bundle.tar.gz /fixture/bundle.tar.gz
RUN mkdir /fixture/release && tar -xzf /fixture/bundle.tar.gz --strip-components=1 -C /fixture/release && rm /fixture/bundle.tar.gz
# This is the only network-enabled phase; use the upstream browser revision.
RUN /fixture/release/runtime/bin/node /fixture/release/runtime/lib/node_modules/playwright/cli.js install --with-deps chromium
COPY browser_extension.py /fixture/browser_extension.py
RUN python3 /fixture/browser_extension.py /fixture/extension.crx /fixture/extension
