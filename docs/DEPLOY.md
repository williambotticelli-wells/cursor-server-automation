# Deploy commands (MIREX tapping experiment)

**Dallinger EC2 list fix:** After refactoring venv or `pip install`, run `./scripts/setup-venv.sh` (or `./scripts/apply-dallinger-ec2-fix.sh`). Then use `dallinger ec2 list instances --all` to see all instances in the account (not just those matching your PEM/key).

---

## MIREX Tapping US (mirex-tapping-us)

### Provision
```bash
dallinger ec2 provision --name mirex-tapping-us --region us-east-2 --dns-host mirex-tapping-us.cap-experiments.com --type m7i.xlarge
```

### Deploy
```bash
EXP_MAX_SIZE_MB=700 psynet deploy ssh \
  --app global-tapping-mirex \
  --dns-host mirex-tapping-us.cap-experiments.com \
  --server mirex-tapping-us.cap-experiments.com
```
Add `--update` when redeploying to an existing app (avoids "app already exists" error).

### Live deployment (mirex-tapping-us)

**Experiment UID:** `bf0a1ca7-51ba-f224-3a66-97d0114f04ed`

**Initial recruitment list (Prolific):**
```
https://global-tapping-mirex.mirex-tapping-us.cap-experiments.com/ad?recruiter=prolific&PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}
```

**Dashboard:**
- URL: https://global-tapping-mirex.mirex-tapping-us.cap-experiments.com/dashboard
- User: `cap`
- Password: `capcapcap2021!`

**Logs:**
- Web: https://logs.mirex-tapping-us.cap-experiments.com (user: `dallinger`, password: `capcapcap2021!`)
- SSH: `ssh -i /Users/ww577/cap.pem ubuntu@mirex-tapping-us.cap-experiments.com docker compose -f '~/dallinger/global-tapping-mirex/docker-compose.yml' logs -f`

**Other:** Experiment directory size ~136 MB; study created on Prolific.

### Export data
```bash
psynet export ssh \
  --app global-tapping-mirex \
  --server mirex-tapping-us.cap-experiments.com \
  --path /Volumes/SSD/Tapping/Data/raw-data/mirex-tap-data \
  --legacy
```
If you get 502 Bad Gateway, use `--legacy` to retry the export locally.
Export path: `mirex-tap-data` in `SSD/Tapping/Data/raw-data`.

### Destroy app (before clean redeploy)
```bash
echo "y" | psynet destroy ssh global-tapping-mirex --server mirex-tapping-us.cap-experiments.com
```

### Teardown
```bash
# 1. Export data first! Then destroy app:
psynet destroy ssh --app global-tapping-mirex --server mirex-tapping-us.cap-experiments.com

# 2. Terminate EC2 server:
dallinger ec2 teardown --name mirex-tapping-us --region us-east-2 --dns-host mirex-tapping-us.cap-experiments.com
```

---

## Other servers (reference)

### zohar-validation-fr (eu-west-3)
```bash
dallinger ec2 teardown --name zohar-validation-fr --region eu-west-3 --dns-host zohar-validation-fr.cap-experiments.com
```

### zohar-valid (us-east-2)
```bash
dallinger ec2 teardown --name zohar-valid --region us-east-2 --dns-host zohar-valid.cap-experiments.com
```

---

## Legacy (wtbw-prolific)
**Destroy existing app (e.g. before switching app name):**
```bash
psynet destroy ssh --app global-tapping-prolific-3 --server wtbw-prolific.cap-experiments.com
```

**Deploy:**
```bash
EXP_MAX_SIZE_MB=700 psynet deploy ssh \
  --app global-tapping-prolific \
  --dns-host wtbw-prolific.cap-experiments.com \
  --server wtbw-prolific.cap-experiments.com
```

---

---

## Pre-flight checklist (MIREX tapping)

| Check | Status | Notes |
|-------|--------|-------|
| MIREX WAVs | ✅ | 20 WAVs at `static/mirex/train1.wav`–`train20.wav` (or S3 for deploy) |
| config (custom_config.py) | ✅ | STIM_BEGINNING=4000, MARKERS_BEGINNING=2000 → music 2 s after first marker |
| MIREX ground truth offset | ✅ | Use `tap_s - 2.0` when comparing to MIREX .txt ground truth |
| audio_filename in export | ✅ | In node definition & stim_info → merge → KDE/asynchrony maps to trainN.txt |
| filter_and_add_markers_no_onsets | ✅ | Uses config_params (config.py) |
| Progress stages | ✅ | 3.5 s wait before "START TAPPING!"; first marker at 2 s |
| Duration | ✅ | ~4 s lead-in + 30 s music ≈ 34 s; duration_rec from actual audio |

---

## Troubleshooting

**If deploy fails with "no space left on device":**
1. SSH into the server: `ssh -i ~/cap.pem ubuntu@<server>.cap-experiments.com`
2. Free disk space by pruning Docker:
   ```bash
   docker system prune -a -f
   docker builder prune -a -f
   ```
3. Retry the deploy.
