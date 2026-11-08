#!/usr/bin/env bash
lists_group() {
    absent soar lists get "$N" || return
    defer soar_cleanup lists "$N"
    expect_fail "$S" soar lists create --name "$N" --yes
    printf '[]\n' > "$T/empty-list.json"
    expect_fail "$S" soar lists create --name "$N" --file "$T/empty-list.json" --yes
    printf '[["fixture","one"]]\n' > "$T/list.json"
    capture "$T/list-create.json" "$S" soar lists create --name "$N" --file "$T/list.json" --yes --json || return
    expect_ok "$S" soar lists import --name "$N" --file "$T/list.json" --yes
    printf '[["fixture","updated"]]\n' > "$T/list-updated.json"
    expect_ok "$S" soar lists update "$N" --file "$T/list-updated.json" --yes
    expect_ok "$S" soar lists add-row "$N" --values 'extra,row' --yes
    check_json 'd[0]["content"] == [["fixture","updated"],["extra","row"]]' soar lists get "$N"
    expect_ok "$S" soar lists remove-row "$N" --index 1 --yes
    expect_ok "$S" soar lists export "$N" --format json --out "$T/list-export.json"
    assert_json "$T/list-export.json" 'd == [["fixture","updated"]]'
    expect_ok "$S" soar lists export "$N" --format csv --out "$T/list-export.csv"
    expect_ok "$S" soar lists list --json
    check_json 'd[0]["content"] == [["fixture","updated"]]' soar lists get "$N"
    expect_ok "$S" soar lists delete "$N" --yes
    absent soar lists get "$N"
}
if soar_selected 40-lists; then
    step '40-lists'
    lists_group
fi
