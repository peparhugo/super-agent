package super_agent.memory_access

default allow = false

risk_rank := {
  "low": 1,
  "medium": 2,
  "high": 3,
  "critical": 4,
}

role_max_risk := {
  "guest": 1,
  "default": 2,
  "operator": 3,
  "worker": 3,
  "admin": 4,
  "system": 4,
}

allow {
  role := input.agent.role
  role_max_risk[role]
  risk_rank[input.memory.risk_level] <= role_max_risk[role]
  not input.memory.contains_instruction
}

deny_reason[msg] {
  input.memory.contains_instruction
  msg := "retrieved memory flagged as instruction"
}

deny_reason[msg] {
  role := input.agent.role
  role_max_risk[role]
  risk_rank[input.memory.risk_level] > role_max_risk[role]
  msg := "memory risk exceeds role limit"
}

reason := deny_reason
