FROM ubuntu:24.04
# Match scripts/install.py's Ubuntu 24.04 runtime dependencies, then add fixtures.
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    at-spi2-core bubblewrap ca-certificates dbus-x11 ffmpeg \
    libasound2t64 libatk-bridge2.0-0t64 libatk1.0-0t64 libatspi2.0-0t64 \
    libc6 libcairo2 libcups2t64 libdbus-1-3 libdrm2 libexpat1 \
    libgbm1 libgcc-s1 libgdk-pixbuf-2.0-0 libgl1 libglib2.0-bin \
    libglib2.0-0t64 libgtk-3-0t64 libnotify4 libnspr4 libnss3 \
    libpango-1.0-0 libssl3t64 libstdc++6 libtss2-esys-3.0.2-0t64 \
    libtss2-mu-4.0.1-0t64 libtss2-tcti-device0t64 libudev1 libusb-1.0-0 \
    libx11-6 libx11-xcb1 libxcb-dri3-0 libxcb1 libxcomposite1 \
    libxdamage1 libxext6 libxfixes3 libxi6 libxkbcommon0 libxrandr2 \
    libxtst6 mesa-vulkan-drivers pulseaudio pulseaudio-utils python3 \
    x11-utils xdg-utils xz-utils \
    python3-gi gir1.2-gtk-3.0 xvfb openbox xdotool \
    xfce4-session xfwm4 xfdesktop4 xfce4-panel curl binutils \
    && rm -rf /var/lib/apt/lists/*
