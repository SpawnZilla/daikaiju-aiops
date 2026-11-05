# Incident loop

Reference code for the self-healing incident loop: how a watchdog escalates a failure it could not fix, and how a reasoning agent and a signed ticket turn it into one allowlisted repair.

```
watchdog (edge node)  ->  signed incident message  ->  intake host
   -> read-only diagnosis -> review step -> signed ticket
   -> forced SSH command -> ticket runner -> one allowlisted fix script
```

- `watchdog/` runs on the watchdog node: the incident library (attempt cap 4, flap guard), the missing-image repair (`fm12`), the docker-events trigger, the incident publisher, the ticket runner and the startup-grace patch.
- `intake/` and `orchestrator/` run on the intake host (systemd units included).
- `tests/test_fm12_mocked.sh` runs the repair against a mocked docker: `bash tests/test_fm12_mocked.sh watchdog/fm12_missing_image_snapshot.sh`.

Addresses (192.0.2.x), ports (`<port>`), paths and topic names are placeholders. Replace them with your own values, and generate your own signing key; never reuse an example key. Install by hand; this is not part of `install.sh` yet.
