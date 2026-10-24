# Plane — branch `inzopr`

Fork Plane'a używany w projekcie na Inżynierię oprogramowania. Zmiany względem upstreamu są oznaczone w kodzie komentarzem `Custom addition (fork)`.

## Wersje

Tag = wersja upstreamu + własny numer: `v1.4.2-inzopr.1`, `v1.4.2-inzopr.2`, …, po przejściu na nowy Plane `v1.4.3-inzopr.1`.

Wypchnięcie tagu uruchamia `.github/workflows/inzopr-images.yml`, który buduje i wrzuca do GHCR obrazy z tym samym tagiem:

- `ghcr.io/bonk-dev/plane-backend` (api, worker, beat-worker, migrator)
- `ghcr.io/bonk-dev/plane-frontend` (web)
- `ghcr.io/bonk-dev/plane-space` (space)

admin, live i proxy nie są zmienione — zostają obrazy `makeplane/*` z upstreamu.

## Wydanie nowej wersji

```bash
git switch inzopr
git tag v1.4.2-inzopr.2
git push origin inzopr v1.4.2-inzopr.2
```

## Wdrożenie na VPS

Instalacja z `deployments/cli/community` (`docker-compose.yaml` + `plane.env`). Obok nich kładziemy `docker-compose.override.yml` z tego katalogu, a w `plane.env` ustawiamy:

```env
APP_RELEASE=v1.4.2              # bazowa wersja upstreamu (admin, live, proxy)
INZOPR_RELEASE=v1.4.2-inzopr.1  # nasze obrazy
```

```bash
docker compose -f docker-compose.yaml -f docker-compose.override.yml --env-file plane.env pull
docker compose -f docker-compose.yaml -f docker-compose.override.yml --env-file plane.env up -d
```

`install.sh` wywołuje compose z samym `-f docker-compose.yaml`, więc pomija override — do uruchamiania używamy powyższych komend.

Jeśli pakiety w GHCR są prywatne, na VPS trzeba się zalogować tokenem z uprawnieniem `read:packages`: `docker login ghcr.io`.

Przed wdrożeniem wersji z nowymi migracjami: backup bazy (`pg_dump`). Migracje uruchamia kontener `migrator` przy starcie.

## Aktualizacja do nowej wersji Plane

```bash
git fetch https://github.com/makeplane/plane.git refs/tags/v1.4.3:refs/tags/v1.4.3 --no-tags
git switch inzopr
git merge v1.4.3
```

Jeśli upstream doda migrację o tym samym numerze co nasze (`0123_issueworklog`, `0124_estimate_type_time`), nie zmieniamy nazw naszych migracji (są już zastosowane na produkcji), tylko dodajemy migrację scalającą: `python manage.py makemigrations --merge`.
