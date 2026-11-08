#!/usr/bin/env bash
# Only reads existing users and roles. GET /token returns a hash, never mints one.
if soar_selected 90-users-roles; then
    step "90-users-roles"
    if capture "$T/users.json" "$S" soar users list --json; then
        U=$(json_value "$T/users.json" 'd[0]["id"] if d else ""') || U=''
        if [ -n "$U" ]; then
            expect_ok "$S" soar users get "$U" --json
        else
            skip '90-users-roles users get: no visible users'
        fi
    fi
    if capture "$T/automation-users.json" "$S" soar users list --type automation --json; then
        U=$(json_value "$T/automation-users.json" 'd[0]["id"] if d else ""') || U=''
        if [ -n "$U" ]; then
            expect_ok "$S" soar users token "$U" --json
        else
            skip '90-users-roles users token: no existing automation user'
        fi
    fi
    if capture "$T/roles.json" "$S" soar roles list --json; then
        R=$(json_value "$T/roles.json" 'd[0]["id"] if d else ""') || R=''
        if [ -n "$R" ]; then
            expect_ok "$S" soar roles get "$R" --json
        else
            skip '90-users-roles roles get: no visible roles'
        fi
    fi
fi
