package super_agent.promotion

default allow = false

risk_rank := {
  "low": 1,
  "medium": 2,
  "high": 3,
  "critical": 4,
}

role_max_risk := {
  "worker": 2,
  "reviewer": 3,
  "admin": 4,
  "system": 4,
}

allow {
  role := input.agent.role
  role_max_risk[role]
  risk_rank[input.candidate.risk_level] <= role_max_risk[role]
}

deny_reason[msg] {
  role := input.agent.role
  not role_max_risk[role]
  msg := "role is not authorized to promote candidates"
}

deny_reason[msg] {
  role := input.agent.role
  role_max_risk[role]
  risk_rank[input.candidate.risk_level] > role_max_risk[role]
  msg := "candidate risk exceeds promotion limit"
}

reason := deny_reason
