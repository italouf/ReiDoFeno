#!/usr/bin/env bats
# Testes BATS para infra/backup/backup.sh e apply-retention.sh

setup() {
    TEST_DIR="$(mktemp -d)"
    export BACKUP_LOCAL="$TEST_DIR/backups"
    export BACKUP_LOG="$TEST_DIR/backup.log"
    export PROJECT_DIR="$TEST_DIR/project"
    mkdir -p "$PROJECT_DIR/infra" "$PROJECT_DIR/media"
    printf 'DJANGO_SECRET_KEY=test\n' > "$PROJECT_DIR/.env.docker"
    printf 'DB_PASSWORD=test\n' > "$PROJECT_DIR/infra/.env"
    printf 'name: reidofeno\n' > "$PROJECT_DIR/infra/docker-compose.yml"
    printf 'localhost {}\n' > "$PROJECT_DIR/infra/Caddyfile"
    printf '# transport\n' > "$PROJECT_DIR/infra/transport.caddy"
    printf '* * * * * true\n' > "$PROJECT_DIR/infra/crontab"
    printf 'media' > "$PROJECT_DIR/media/sample.txt"
}

teardown() {
    rm -rf "$TEST_DIR"
}

@test "backup gera dump PostgreSQL válido" {
    run ./infra/backup/backup.sh --dry-run
    [ "$status" -eq 0 ]
    [ -f "$BACKUP_LOCAL/db.dump" ]
    run pg_restore --list "$BACKUP_LOCAL/db.dump"
    [ "$status" -eq 0 ]
}

@test "config é criptografada com age" {
    run ./infra/backup/backup.sh --dry-run
    [ "$status" -eq 0 ]
    [ -f "$BACKUP_LOCAL/config.tar.gz.age" ]
    run head -n 1 "$BACKUP_LOCAL/config.tar.gz.age"
    [[ "$output" =~ "age-encryption.org" ]]
}

@test "retenção remove dumps antigos" {
    mkdir -p "$BACKUP_LOCAL"
    for i in {1..10}; do
        touch -d "$i days ago" "$BACKUP_LOCAL/db-$(date -d "$i days ago" +%F).dump"
    done
    run ./infra/backup/apply-retention.sh "$BACKUP_LOCAL"
    [ "$status" -eq 0 ]
    count=$(ls "$BACKUP_LOCAL"/db-*.dump | wc -l)
    [ "$count" -le 7 ]
}
