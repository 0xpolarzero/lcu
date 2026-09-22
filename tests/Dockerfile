FROM ubuntu:24.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates python3 python3-gi gir1.2-gtk-3.0 xvfb openbox dbus-x11 at-spi2-core libxtst6 libxfixes3 libxcomposite1 libxdamage1 libxi6 libxrandr2 x11-utils xdotool curl binutils xz-utils && rm -rf /var/lib/apt/lists/*
