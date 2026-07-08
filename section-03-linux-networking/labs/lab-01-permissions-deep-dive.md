# Lab 1 — Permissions deep dive

**Goal:** go from "I can read `ls -l`" to "I can read, set, and *audit* every permission bit on a Linux box" — octal, the x-bit's split personality on directories, the three special bits (setuid, setgid, sticky), and `umask`. All inside vps-lab, as a normal user, because that's the only way permissions are real.

## The mental map (read this first)

In Section 1 Lab 3 you met the two halves of every file: an **owner name-tag** (owner *user* + owner *group*) and a **rulebook** (`rwx` for owner / group / others). You also learned the rule that makes this lab tricky: **root skips permission checks entirely.** That's why, logged in as root, everything "just works" and you never *feel* a permission. So this whole lab is done as **`mahadi`** (a normal user), and we bring in a second user to feel the group/other columns bite.

Here is the full anatomy of one `ls -l` line — every character has a job:

```
 -rwxr-x---  1  mahadi  devs   4096  Jul 9 10:00  deploy.sh
 │└┬┘└┬┘└┬┘     └──┬──┘ └─┬┘
 │ │  │  │         │      │
 │ │  │  └ others  │      └ owner GROUP (the group's column applies to its members)
 │ │  └─ group     └ owner USER (the owner column applies to this person)
 │ └──── owner (user)
 └─────── type: - file, d dir, l symlink, c/b device, s socket
```

Two mental models to hold:

1. **Octal is just the rulebook in base 8.** Each of the three columns (owner/group/other) is one digit, `r=4 w=2 x=1` added up. `rwx = 7`, `r-x = 5`, `rw- = 6`. So `rwxr-x---` = **750**. When you `chmod 750 file` you're writing the whole rulebook in three digits. This is *the* dialect of every CKA question and every Dockerfile — you already used it (`chmod 700 .ssh`, `600 authorized_keys` in the vps-lab Dockerfile).

2. **`x` means two completely different things on a file vs a directory** — this is the single most-missed idea in Linux permissions:
   - on a **file**: `x` = "you may run this as a program".
   - on a **directory**: `x` = "you may *enter/traverse* it" (`cd` into it, or reach anything through it). `r` on a dir only lets you *list the names*; without `x` you can't `cd` in or `stat` what's inside even if you can see the names. A directory with `r` but no `x` is a taunt: you see the labels, you can't open the drawer.

Then three **special bits** that sit on top, and one **filter** (`umask`) that decides the default rulebook for everything you create. We'll meet each live.

## Steps

> Everything here runs **inside vps-lab**. Get in:
> ```bash
> # on your Mac
> ssh -i vps-lab/keys/vps_key -p 9022 mahadi@localhost
> ```
> Your prompt becomes `mahadi@vps-lab`. If the connect fails, see Lab 4 step 2 (the reimage ritual) to restore vps-lab.

### 1. Octal ⇄ symbolic until it's reflex

```bash
# inside vps-lab
cd ~
touch deploy.sh
ls -l deploy.sh
```

Fresh file, no `x`:

```
-rw-r--r-- 1 mahadi mahadi 0 Jul  9 10:00 deploy.sh
```

Read it: `rw-` owner (6), `r--` group (4), `r--` other (4) → **644**. (Why 644 and not 666? That's `umask`, step 5.) Now set it two ways and confirm they land identically:

```bash
chmod 750 deploy.sh          # octal: the whole rulebook in one shot
ls -l deploy.sh              # -rwxr-x---
chmod u=rwx,g=rx,o= deploy.sh   # symbolic: same result, spelled out
ls -l deploy.sh              # -rwxr-x---  (identical)
```

`chmod 750` and `chmod u=rwx,g=rx,o=` are the same edit. Symbolic is for *tweaks* (`chmod +x script`, `chmod o-r secret`); octal is for *stating the whole rulebook* and is what you'll read in every manifest. Convert in your head: `-rwxr-x---` → 7,5,0. Do it now with a few: what's `rw-rw-r--`? (664.) `r-xr-xr-x`? (555.)

### 2. The directory x-bit — the trap that bites everyone

```bash
mkdir vault
echo "the launch codes" > vault/secret.txt
chmod 644 vault          # rw-r--r-- : readable, but NO x → not traversable
ls -l vault/secret.txt   # this works — you're reading vault's ENTRY LIST (needs r)
cat vault/secret.txt     # this FAILS — reaching INTO vault needs x
```

Expect the last line to fail:

```
cat: vault/secret.txt: Permission denied
```

Sit with this: you can `ls` the directory (you have `r` — you see the *names*) but you cannot `cat` a file inside it (you lack `x` — you can't *traverse* to reach it), **even though the file itself is `644` and readable.** The directory's missing `x` is a locked turnstile in front of a room full of unlocked doors. Fix it and the file becomes reachable:

```bash
chmod 755 vault          # add x back
cat vault/secret.txt     # now works: "the launch codes"
```

This is why deploy scripts fail with "Permission denied" on a file that *looks* readable — some parent directory in the path lost its `x`. The permission check runs on **every** component of the path, left to right.

### 3. setuid — "run as the file's owner, not as you"

Some programs must do something only root may do, on behalf of a normal user. The classic is `passwd`: you (a normal user) change your password, which writes to `/etc/shadow` (owned by root, `640`, unreadable to you). How? A **setuid** bit:

```bash
ls -l /usr/bin/passwd
```

```
-rwsr-xr-x 1 root root 59976 ... /usr/bin/passwd
      ↑
      's' where owner's 'x' should be = the setuid bit
```

That `s` means: **when anyone runs this file, the process runs with the file's OWNER's identity (root), not the caller's.** So `passwd` momentarily becomes root, edits `/etc/shadow`, and drops back. Make one yourself and prove it changes the running identity:

```bash
cp /bin/id ~/myid
sudo chown root:root ~/myid
sudo chmod 4755 ~/myid        # the leading 4 = setuid; 755 = the normal rwxr-xr-x
ls -l ~/myid                  # -rwsr-xr-x ... root root
~/myid                        # run it as mahadi...
```

`id` prints who the process *effectively* is. Run normally it says `uid=1000(mahadi)`; run via your setuid copy it reports an **effective uid of 0 (root)** even though *you* launched it:

```
uid=1000(mahadi) gid=1000(mahadi) euid=0(root) groups=...
```

`euid=0` = "effective user is root". **This is why setuid binaries are the #1 privilege-escalation hunting ground** — a buggy setuid-root program is a root shell waiting to happen. Which is exactly what the audit in step 6 finds. Clean it up so you don't leave a footgun:

```bash
rm ~/myid
```

### 4. setgid & the sticky bit — the two directory bits

**Sticky bit** — the `/tmp` problem. `/tmp` is world-writable (`777`) so *anyone* can create files there. Without protection, anyone could also *delete anyone else's* files (delete permission comes from the **directory's** `w`, not the file's). The sticky bit fixes that:

```bash
ls -ld /tmp
```

```
drwxrwxrwt 10 root root 4096 ... /tmp
         ↑
         't' where other's 'x' should be = the sticky bit
```

`t` means: **in this directory, you can only delete files you own**, even though everyone can write. Octal `1777`. Every shared-writable dir on earth (`/tmp`, `/var/tmp`) has it.

**setgid on a directory** — the "shared team folder" bit. Normally a new file gets *your* primary group. setgid on the parent dir makes new files inherit the *directory's* group instead — so a whole team's files stay group-readable without anyone remembering to `chgrp`:

```bash
sudo groupadd devs 2>/dev/null; sudo usermod -aG devs mahadi   # (may already exist)
mkdir ~/shared
sudo chgrp devs ~/shared
chmod 2775 ~/shared           # leading 2 = setgid; ls shows 's' in the group column
ls -ld ~/shared               # drwxrwsr-x ... mahadi devs
touch ~/shared/from-mahadi
ls -l ~/shared/from-mahadi    # group is 'devs' (inherited), not 'mahadi'
```

Without setgid the new file's group would be `mahadi`; with it, the file inherited `devs` from the folder. The leading octal digit is the special-bits nibble: **4=setuid, 2=setgid, 1=sticky** (same 4/2/1 as rwx, one row up).

### 5. umask — why new files are 644 and not 666

You never explicitly set 644 in step 1, yet that's what `touch` produced. The **umask** is a *subtraction filter*: the system's base is `666` for files (`777` for dirs — dirs need x to be usable), and umask's bits are **removed**.

```bash
umask            # 0022  — the default on Debian
umask -S         # u=rwx,g=rx,o=rx  — the same thing, as what's ALLOWED
```

`0022` means "strip write from group and other". Base file `666` minus `022` = **644**. Base dir `777` minus `022` = **755**. That's every default you've ever seen, explained. Prove you can move it:

```bash
umask 077                      # strip ALL group+other bits — "private by default"
touch private.txt; ls -l private.txt   # -rw------- (600)
mkdir privatedir; ls -ld privatedir    # drwx------ (700)
umask 0022                     # put it back for the rest of the session
```

`umask 077` is exactly what hardening guides mean by "make new files private by default" — and it's why your `~/.ssh` keys were born `600` in Lab 5 (ssh-keygen sets it, but a tight umask is the belt-and-braces). umask is **per-process, inherited from the shell**; a service's umask is set in its unit file (Lab 2's systemd-on-paper).

### 6. Audit like an ops engineer — `find` by permission

The real skill isn't setting bits, it's *finding* the dangerous ones on a box you didn't build. `find -perm` is the tool:

```bash
# every setuid-root binary on the system (the privesc audit — run this on any new box)
sudo find / -perm -4000 -type f 2>/dev/null

# world-writable files (anyone can edit — config-tampering risk)
sudo find / -perm -0002 -type f -not -path '/proc/*' -not -path '/sys/*' 2>/dev/null

# files with NO owner (left behind by deleted users — an audit red flag)
sudo find / -nouser 2>/dev/null
```

The `-perm -4000` form means "has **at least** these bits set" (the leading `-`); `-perm 4000` (no dash) would mean "*exactly* these and nothing else". The `2>/dev/null` throws away the "Permission denied" noise from `/proc` (a real directory-x lesson: even root gets told off by some kernel pseudo-files). The first command's list — `passwd`, `sudo`, `su`, `mount`, ping — is the exact set a security review scrutinises: **every setuid-root binary is trust you've extended to that program's authors.**

## Verify

Proof command — build the exact permission puzzle from memory and make it behave:

```bash
# inside vps-lab
mkdir -p /tmp/perms-test/inner && echo hi > /tmp/perms-test/inner/f.txt
chmod 644 /tmp/perms-test/inner        # remove x from the directory
cat /tmp/perms-test/inner/f.txt        # must FAIL: Permission denied
chmod 755 /tmp/perms-test/inner        # restore x
cat /tmp/perms-test/inner/f.txt        # must now print: hi
rm -rf /tmp/perms-test
```

If the `cat` fails then succeeds after the `chmod 755`, you've proved you understand the directory x-bit. Then answer aloud:

**1. `chmod 644` on a directory that contains a `644` file — can you read the file? Why?**

<details><summary>Answer (read after attempting aloud)</summary>

No. Reading a file requires *traversing* every directory in its path, and traversal needs the directory's **x** bit. `644` on a directory is `rw-r--r--` — no x anywhere. You can `ls` the directory (that only needs `r`, to read the name list) but you cannot reach *into* it to open the file, regardless of the file's own permissions. `x` on a directory means "may enter/pass through"; `r` only means "may list names". Fix: `chmod 755` (or `+x`) the directory.

</details>

**2. What does the setuid bit do, and why is `find / -perm -4000` a security audit?**

<details><summary>Answer (read after attempting aloud)</summary>

setuid (`s` in the owner's x slot, octal leading `4`) makes the program run with the **file owner's** identity, not the caller's — so a setuid-root binary runs as root no matter who launches it. That's how `passwd` (a normal user) can write root-owned `/etc/shadow`. `find / -perm -4000` lists every such binary: each one is a program you're trusting to *not* be exploitable into a root shell, so a bug in any of them is a privilege-escalation vector. Reviewing that list (and questioning any non-standard entry) is a standard hardening step.

</details>

**3. `umask` is `0022`. What permissions does a newly-created file get, and a newly-created directory? Show the arithmetic.**

<details><summary>Answer (read after attempting aloud)</summary>

Files: base `666` minus umask `022` = **644** (`rw-r--r--`). Directories: base `777` minus `022` = **755** (`rwxr-xr-x`). umask is a *subtraction* filter that strips bits from the base; `022` strips the write bit from group and other. Directories start from `777` (not `666`) because a directory is useless without its x/traverse bit. A `umask 077` would make files `600` and dirs `700` — "private by default", the hardening default.

</details>

**4. Octal `1777` on `/tmp` — read every digit aloud.**

<details><summary>Answer (read after attempting aloud)</summary>

Leading `1` = the **sticky bit** (in a shared-writable dir, only a file's owner may delete it — stops users deleting each other's `/tmp` files). Then `777` = `rwx` for owner, group, and other — everyone can create files. So `/tmp` is "anyone may write, but nobody may delete what isn't theirs". The leading special-bits digit is 4=setuid, 2=setgid, 1=sticky (same 4/2/1 values as rwx, applied to the special row).

</details>

## Clean up

```bash
# inside vps-lab
rm -rf ~/vault ~/shared ~/deploy.sh ~/private.txt ~/privatedir 2>/dev/null
umask 0022     # in case a shell kept 077
exit           # back to your Mac
```

Nothing you changed touches the running services — this lab was pure Linux muscle. Leave vps-lab running for Lab 2.
