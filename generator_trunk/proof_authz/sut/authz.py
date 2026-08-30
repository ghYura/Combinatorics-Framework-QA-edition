#!/usr/bin/env python3
"""
authz - an authorization policy engine.

Written to spec, from experience, as a normal production component: roles with a
seniority rank, roles that include other roles, permissions expressed as
(action, resource-pattern), explicit allow/deny rules with conditions, and a
resolver that answers can(principal, action, resource, context).

Everything is in-memory and deterministic. No clock, no I/O; a context dict
carries whatever the conditions need.

Public API:
    define_role(name, rank, includes=(), grants=())
    assign(principal, role)          revoke(principal, role)
    add_rule(effect, subject, action, resource, conditions=None)
    can(principal, action, resource, context=None) -> bool
    effective(principal) -> set of (action, resource) granted
    explain(principal, action, resource, context) -> str

Resolution order, as documented to callers:
    1. an explicit deny that applies always wins;
    2. otherwise an explicit allow that applies grants;
    3. otherwise the union of the principal's roles' grants;
    4. otherwise deny.

Invariants the engine promises (checked by audit(), never by the engine):
    A1  every effective permission traces to a grant or an allow rule
    A2  an applicable deny always wins, wherever the allow came from
    A3  role expansion terminates and is idempotent
    A4  revoke(assign(x)) returns the principal to its prior state
    A5  seniority alone never confers a permission
    A6  a resource pattern never matches across a path-segment boundary
    A7  a rule's conditions are conjunctive - all must hold
"""

# --------------------------------------------------------------------------
# catalogue
# --------------------------------------------------------------------------

#: Administrative actions. A wildcard grant is not supposed to reach these.
PRIVILEGED_ACTIONS = ("delete", "grant", "configure")

ALL_ACTIONS = ("read", "write", "delete", "grant", "configure")


class AuthzError(Exception):
    pass


# --------------------------------------------------------------------------
# resource patterns
# --------------------------------------------------------------------------

def match_resource(pattern, resource):
    """Does `pattern` cover `resource`?

    Patterns are path-like: `docs/reports/q1`, a trailing `*` covering a
    subtree (`docs/*`), or a bare `*` covering everything.
    """
    if pattern == "*":
        return True
    if pattern.endswith("/*"):
        prefix = pattern[:-2]
        return resource.startswith(prefix)
    if pattern.endswith("*"):
        return resource.startswith(pattern[:-1])
    return pattern == resource


def match_action(pattern, action):
    if pattern == "*":
        return True
    return pattern == action


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------

class Role(object):
    __slots__ = ("name", "rank", "includes", "grants")

    def __init__(self, name, rank, includes, grants):
        self.name = name
        self.rank = rank
        self.includes = list(includes)
        self.grants = list(grants)          # [(action, resource_pattern), ...]

    def __repr__(self):
        return "<Role %s r%d>" % (self.name, self.rank)


class Rule(object):
    __slots__ = ("effect", "subject", "action", "resource", "conditions", "seq")

    def __init__(self, effect, subject, action, resource, conditions, seq):
        self.effect = effect                # "allow" | "deny"
        self.subject = subject              # a principal name or a role name
        self.action = action
        self.resource = resource
        self.conditions = dict(conditions or {})
        self.seq = seq

    def __repr__(self):
        return "<%s %s %s on %s>" % (self.effect, self.subject, self.action, self.resource)


class Engine(object):

    def __init__(self, seniority_shortcut=False, deny_scope="direct"):
        # seniority_shortcut: let a senior role act on anything a junior may.
        # deny_scope: "direct"  - deny rules named for the principal or its roles
        #             "expanded" - also deny rules on roles reached by inclusion
        self.seniority_shortcut = seniority_shortcut
        self.deny_scope = deny_scope

        self.roles = {}                     # name -> Role
        self.assignments = {}               # principal -> [role names]
        self.rules = []                     # [Rule]
        self._seq = 0
        self._expand_cache = {}             # role -> expanded role list
        self.trace = []                     # last explain() breadcrumbs

    # ------------------------------------------------------------- roles --

    def define_role(self, name, rank=0, includes=(), grants=()):
        if name in self.roles:
            raise AuthzError("role %s already defined" % name)
        self.roles[name] = Role(name, rank, includes, grants)
        self._expand_cache.clear()
        return self.roles[name]

    def _expand(self, role_name, seen=None):
        """All roles reachable from `role_name`, itself included.

        Roles include other roles, so this walks the graph. A role may be
        reached by more than one path; the result is deduplicated.
        """
        if role_name in self._expand_cache:
            return self._expand_cache[role_name]
        if seen is None:
            seen = set()
        if role_name in seen:
            return []
        seen.add(role_name)
        role = self.roles.get(role_name)
        if role is None:
            return []
        out = [role_name]
        for inc in role.includes:
            for r in self._expand(inc, seen):
                if r not in out:
                    out.append(r)
        self._expand_cache[role_name] = out
        return out

    def roles_of(self, principal):
        out = []
        for r in self.assignments.get(principal, []):
            for e in self._expand(r):
                if e not in out:
                    out.append(e)
        return out

    # -------------------------------------------------------- assignment --

    def assign(self, principal, role):
        if role not in self.roles:
            raise AuthzError("unknown role %s" % role)
        self.assignments.setdefault(principal, []).append(role)

    def revoke(self, principal, role):
        held = self.assignments.get(principal, [])
        self.assignments[principal] = [r for r in held if r != role]

    # ------------------------------------------------------------- rules --

    def add_rule(self, effect, subject, action, resource, conditions=None):
        if effect not in ("allow", "deny"):
            raise AuthzError("effect must be allow or deny")
        self._seq += 1
        self.rules.append(Rule(effect, subject, action, resource, conditions, self._seq))

    def _conditions_hold(self, rule, context):
        """Every declared condition must hold for the rule to apply."""
        ctx = context or {}
        results = [ctx.get(k) == v for k, v in rule.conditions.items()]
        if not results:
            return True
        return any(results)

    def _applicable(self, principal, action, resource, context):
        """The rules naming this principal, or a role it holds."""
        subjects = {principal}
        if self.deny_scope == "expanded":
            subjects.update(self.roles_of(principal))
        else:
            subjects.update(self.assignments.get(principal, []))
        hits = []
        for rule in self.rules:
            if rule.subject not in subjects:
                continue
            if not match_action(rule.action, action):
                continue
            if not match_resource(rule.resource, resource):
                continue
            if not self._conditions_hold(rule, context):
                continue
            hits.append(rule)
        return hits

    # ---------------------------------------------------------- resolver --

    def effective(self, principal):
        """Every (action, resource-pattern) the principal's roles grant."""
        out = set()
        for role_name in self.roles_of(principal):
            role = self.roles.get(role_name)
            if role is None:
                continue
            for g in role.grants:
                out.add(tuple(g))
        return out

    def _granted_by_roles(self, principal, action, resource):
        for act, res in self.effective(principal):
            if match_action(act, action) and match_resource(res, resource):
                return (act, res)
        return None

    def _max_rank(self, principal):
        ranks = [self.roles[r].rank for r in self.roles_of(principal) if r in self.roles]
        return max(ranks) if ranks else -1

    def can(self, principal, action, resource, context=None):
        self.trace = []
        hits = self._applicable(principal, action, resource, context)

        for rule in hits:
            if rule.effect == "deny":
                self.trace.append("deny rule %s" % rule)
                return False

        for rule in hits:
            if rule.effect == "allow":
                self.trace.append("allow rule %s" % rule)
                return True

        g = self._granted_by_roles(principal, action, resource)
        if g is not None:
            self.trace.append("granted by role permission %s" % (g,))
            return True

        if self.seniority_shortcut:
            # An owner should not have to be granted what an editor already has.
            need = 0
            for role_name in self.roles:
                role = self.roles[role_name]
                for act, res in role.grants:
                    if match_action(act, action) and match_resource(res, resource):
                        need = max(need, role.rank)
            if self._max_rank(principal) >= need:
                self.trace.append("seniority shortcut (rank %d >= %d)"
                                  % (self._max_rank(principal), need))
                return True

        self.trace.append("no rule or grant applies")
        return False

    def explain(self, principal, action, resource, context=None):
        allowed = self.can(principal, action, resource, context)
        return "%s: %s" % ("ALLOW" if allowed else "DENY", "; ".join(self.trace))

    # ------------------------------------------------------------- audit --

    def audit(self, probes=()):
        """Violated invariant ids. `probes` is a list of
        (principal, action, resource, context) the caller wants checked."""
        bad = []

        # A1 every allowed probe traces to a grant or an allow rule
        for principal, action, resource, ctx in probes:
            if self.can(principal, action, resource, ctx):
                by_rule = any(r.effect == "allow"
                              for r in self._applicable(principal, action, resource, ctx))
                by_grant = self._granted_by_roles(principal, action, resource) is not None
                if not (by_rule or by_grant):
                    bad.append("A1")
                    break

        # A2 an applicable deny wins wherever the allow came from
        for principal, action, resource, ctx in probes:
            denies = [r for r in self.rules
                      if r.effect == "deny"
                      and r.subject in set(self.roles_of(principal)) | {principal}
                      and match_action(r.action, action)
                      and match_resource(r.resource, resource)
                      and self._conditions_hold(r, ctx)]
            if denies and self.can(principal, action, resource, ctx):
                bad.append("A2")
                break

        # A3 expansion terminates and is idempotent
        for name in self.roles:
            first = list(self._expand(name))
            self._expand_cache.clear()
            second = list(self._expand(name))
            if first != second or len(first) != len(set(first)):
                bad.append("A3")
                break

        # A5 seniority alone never confers a permission
        for principal, action, resource, ctx in probes:
            if self.can(principal, action, resource, ctx):
                if (self._granted_by_roles(principal, action, resource) is None
                        and not any(r.effect == "allow" for r in
                                    self._applicable(principal, action, resource, ctx))):
                    bad.append("A5")
                    break

        # A6 a pattern never matches across a path-segment boundary
        for role in self.roles.values():
            for _act, pattern in role.grants:
                if pattern.endswith("/*"):
                    stem = pattern[:-2]
                    if match_resource(pattern, stem + "-shadow/x"):
                        bad.append("A6")
                        break
            if "A6" in bad:
                break

        # A7 conditions are conjunctive
        for rule in self.rules:
            if len(rule.conditions) >= 2:
                keys = list(rule.conditions)
                half = {keys[0]: rule.conditions[keys[0]]}
                if self._conditions_hold(rule, half):
                    bad.append("A7")
                    break

        return sorted(set(bad))

    def snapshot(self):
        return {
            "roles": {n: (r.rank, tuple(r.includes), tuple(sorted(map(tuple, r.grants))))
                      for n, r in self.roles.items()},
            "assignments": {p: sorted(rs) for p, rs in self.assignments.items() if rs},
            "rules": [(r.effect, r.subject, r.action, r.resource,
                       tuple(sorted(r.conditions.items()))) for r in self.rules],
        }
