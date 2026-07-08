FROM debian:12-slim
# a bare Debian — the closest thing to what a hosting provider hands you

RUN apt-get update && apt-get install -y --no-install-recommends \
        openssh-server sudo curl vim iproute2 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir /run/sshd
# one RUN = one layer: the apt catalog downloaded by `update` is deleted in the
# SAME layer, so it never ships (layers are append-only — a later rm hides, not shrinks)
# mkdir /run/sshd: sshd's privilege-separation dir — normally systemd creates it
# at boot; no systemd here, so we do its one job ourselves

# The user you'll log in as — passwordless sudo, like a fresh VPS after cloud-init
RUN useradd --create-home --shell /bin/bash mahadi \
    && echo 'mahadi ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/mahadi
# a drop-in file under sudoers.d, never editing /etc/sudoers itself —
# standard practice: drop-ins are additive, reviewable, and can't corrupt the main file

# Key-only auth — the two lines every real server gets hardened with
RUN sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config \
    && sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
# the ^#\? regex catches the line whether Debian shipped it commented out or not

COPY keys/vps_key.pub /home/mahadi/.ssh/authorized_keys
# installing the LOCK (public half) — the private key never enters the image

RUN chown -R mahadi:mahadi /home/mahadi/.ssh \
    && chmod 700 /home/mahadi/.ssh && chmod 600 /home/mahadi/.ssh/authorized_keys
# not decoration: sshd's StrictModes REFUSES keys whose file permissions are loose —
# if others could edit your authorized_keys, they could add their own lock

EXPOSE 22
CMD ["/usr/sbin/sshd", "-D"]
# -D = "don't daemonize" — Lab 1's foreground rule: sshd must BE PID 1,
# because the daemonizing parent would exit and kill the container