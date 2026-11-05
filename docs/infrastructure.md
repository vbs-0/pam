# Infrastructure: from domain to running server

How `pam.is-cool.dev` goes from nothing to a running site: the domain, the VM, the firewall rules at each layer, DNS and
the base server. [`deploy.md`](deploy.md) covers shipping new versions of PAM itself; this page is the groundwork under it.

```
 browser ──HTTPS──▶ pam.is-cool.dev (A record) ──▶ 129.159.20.37
                                                     │
                      OCI security list (cloud firewall, per VCN)
                                                     │
                      host firewall (iptables; ufw is not enabled)
                                                     │
                nginx :80/:443 ─┬─ /api, /docs, /healthz ─▶ uvicorn 127.0.0.1:8100 ─▶ Postgres 127.0.0.1:5432
                                └─ everything else ───────▶ /opt/pam/www (web console, APK downloads)
```

## 1. The domain

There is no purchased domain. `is-cool.dev` is a free shared domain handed out as subdomains by **Open Domains**.

1. Create an account on the Open Domains dashboard and use **Request domain** to ask for a subdomain of `is-cool.dev`
   (here: `pam`, giving `pam.is-cool.dev`).
2. Requests are reviewed by volunteers. The dashboard warned that reviews were taking about a week, so request the
   name early. Until it is approved the DNS tab stays empty.
3. Once approved, the domain appears under **My domains**. Open it to manage its DNS records (section 4).

What you get is a name you can point at an IP address. You do not get a mailbox, mail hosting, or SMTP credentials,
and you may not be able to add every record type. See [Mail](deploy.md#mail) for how sending works regardless.

## 2. The VM

Oracle Cloud (OCI) compute instance:

| Setting | Value |
|---|---|
| Image | Ubuntu 22.04 LTS |
| Size | 2 vCPU, ~1 GB RAM (956 MB usable) plus 2 GB swap |
| Network | VCN `vbsvnc`, public subnet, a public IPv4 address (`129.159.20.37`) |
| Login | SSH key only; the instance has no password login |

Steps in the OCI console: **Compute → Instances → Create instance**, pick the Ubuntu 22.04 image, keep the default VCN
and public subnet with a public IP, and download or paste an SSH public key. Note the public IP once it is running.

Connect and name the host so every command can say `ssh vbs`. In `~/.ssh/config` on your own machine:

```
Host vbs
    HostName 129.159.20.37
    User ubuntu
    IdentityFile ~/.ssh/<your-private-key>
```

Treat the IP as permanent only if it is a **reserved** public IP. An ephemeral one changes when the instance is
recreated, and the A record must then be updated.

## 3. Security rules (three layers)

Traffic has to get past three layers. Know which one is blocking when something cannot connect.

### 3a. OCI security list (cloud firewall)

Console path: **Networking → Virtual cloud networks → vbsvnc → Security Lists → Default Security List for vbsvnc**.
Rules are stateful (a reply to allowed traffic is allowed back).

**What it should contain for PAM:**

| Direction | Source or destination | Protocol / port | Why |
|---|---|---|---|
| Ingress | 0.0.0.0/0 | TCP 22 | SSH (key only) |
| Ingress | 0.0.0.0/0 | TCP 80 | HTTP, for the HTTPS redirect and Let's Encrypt |
| Ingress | 0.0.0.0/0 | TCP 443 | HTTPS |
| Ingress | 0.0.0.0/0 | ICMP types 3 and 4 | path MTU discovery (OCI default) |
| Egress | 0.0.0.0/0 | all | updates, certbot, SMTP relay |

No ingress is needed for 8100 (the API), 5432 (Postgres), 587 (outbound mail) or 25.

**What it contains today, honestly:** besides the four rows above, the list still carries rules from earlier projects:
ingress for TCP 5173, 8000 and 25, and several "All Protocols from 0.0.0.0/0" rows. In effect the cloud firewall allows
everything. Nothing is exposed by it right now only because nothing but SSH and nginx listens on a public address
(`ss -tlnp` shows the API and Postgres on `127.0.0.1`). It is not defence in depth. To tighten it, delete every ingress
row except the table above (Security List → select a rule → **Remove**), then re-check that SSH and the site still work
before closing the console.

### 3b. Port 25

Oracle blocks **outbound** port 25 for the whole account. Opening an egress or ingress rule for 25 does not change
that, and the IP has no reverse DNS, so the VM cannot deliver mail itself. Outbound mail goes through an SMTP relay on
port 587 instead (see [Mail](deploy.md#mail)). Port 587 needs no rule: the default egress rule already allows it.

### 3c. Host firewall

`ufw` is installed but **inactive**. iptables has policy `INPUT ACCEPT` plus a handful of ACCEPT rules for 80, 443,
loopback and established traffic, and stale ones for 5173, 8000 and 5000 left over from other projects. Nothing listens
on those three ports, so they are inert, but they should be removed. A tidy replacement that leaves SSH, HTTP and HTTPS
open:

```bash
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
sudo ufw enable        # keep your current SSH session open and test a second one before closing the first
```

Note that on Oracle images the stock iptables rules can sit ahead of ufw, so confirm with `sudo iptables -S INPUT`
afterwards.

## 4. DNS

Records are edited in the Open Domains dashboard (**My domains → the domain → DNS records**).

| Name | Type | Content | Proxy | Notes |
|---|---|---|---|---|
| `pam.is-cool.dev` | A | `129.159.20.37` | DNS only (grey cloud) | the site, API and TLS validation |
| `info.pam.is-cool.dev` | A | `129.159.20.37` | DNS only | unused; nginx has no site or certificate for it. Delete it or give it a purpose |

Keep the proxy off: Let's Encrypt validates over plain HTTP on port 80 straight to the server, and a proxy in front
adds a second certificate layer you would then also have to manage.

Check propagation from your machine (it usually takes minutes, rarely hours):

```bash
nslookup pam.is-cool.dev          # should return 129.159.20.37
curl -I http://pam.is-cool.dev    # should answer from nginx (a redirect to https once TLS is installed)
```

Mail DNS: none is needed for the current Gmail relay. A relay that sends from your own domain (SMTP2GO, Brevo) gives you
CNAME or TXT records for SPF and DKIM to add here, if your dashboard allows those record types.

## 5. Base server setup

Everything below is already done on `vbs`; this is the order to repeat it on a fresh VM.

1. **Update and unattended security updates**
   ```bash
   sudo apt update && sudo apt -y upgrade && sudo apt -y install unattended-upgrades nginx postgresql certbot python3-certbot-nginx
   ```
2. **Swap**: the 1 GB box also has two 1 GB swap files, which absorb short spikes during pipeline runs. Do not rely on
   swap for steady load.
3. **Time zone**: leave it at UTC. PAM stores UTC and converts to IST (Asia/Kolkata) only for business dates.
4. **SSH hardening** (`/etc/ssh/sshd_config`): `PasswordAuthentication no`, `PubkeyAuthentication yes`. Root login is
   key-only (`PermitRootLogin without-password`). Reload with `sudo systemctl reload ssh`.
5. **Postgres**: listens on `localhost` only (`listen_addresses`). Create role `pam` and databases `pam` and `pam_test`
   owned by it; revoke `CONNECT` from `PUBLIC`. Details in [`dev-setup.md`](dev-setup.md).
6. **App user and service**: the `pam` system user, `pam-api.service` and the nginx site, as in
   [`deploy.md`](deploy.md#first-time-setup-what-was-done-once).
7. **TLS**: `sudo certbot --nginx -d pam.is-cool.dev --redirect`. Certbot installs a systemd timer that renews the
   certificate automatically (about 60 days after issue); check with `sudo certbot renew --dry-run`.
8. **Remove what is not yours**: when this VM was inherited it was running other projects (a second site, an HR app, an
   anime backend, Redis, Docker). Those were stopped and disabled so the 1 GB box is not shared with them:
   ```bash
   sudo systemctl disable --now <service>
   ```
   They are disabled, not deleted, so they can be restored. A leftover Let's Encrypt certificate for the old site is still
   renewing; remove it with `sudo certbot delete --cert-name <name>` once that project is gone for good.

## 6. Verify the whole chain

```bash
nslookup pam.is-cool.dev                              # DNS points at the VM
curl -sI https://pam.is-cool.dev | head -1            # TLS + nginx: HTTP/1.1 200 OK
curl -s https://pam.is-cool.dev/readyz                # API + database: {"status":"ready"}
ssh vbs "sudo ss -tlnp"                               # only 22, 80, 443 on 0.0.0.0; 8100 and 5432 on 127.0.0.1
ssh vbs "sudo certbot certificates"                   # expiry date in the future
```

## 7. Known gaps

- The OCI security list and host firewall are wider than they need to be (section 3). Nothing is exposed today, but
  tightening them is the single most useful hardening step left.
- No monitoring or alerting; the API is checked by `/readyz` during deploys only.
- Backups: Postgres has no scheduled dump. The dataset is regenerable from the seed, but real (user-entered)
  households exist only in the database. A nightly `pg_dump` to somewhere off the VM is the next step.
- Single VM, single API worker: a reboot is downtime.
