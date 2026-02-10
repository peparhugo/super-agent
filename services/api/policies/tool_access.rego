package super_agent.tool_access

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

role_profiles := {
  "guest": {"sandbox_low"},
  "default": {"sandbox_low", "sandbox_standard"},
  "operator": {"sandbox_low", "sandbox_standard", "sandbox_sensitive"},
  "worker": {"sandbox_low", "sandbox_standard"},
  "admin": {"sandbox_low", "sandbox_standard", "sandbox_sensitive", "sandbox_privileged"},
  "system": {"sandbox_low", "sandbox_standard", "sandbox_sensitive", "sandbox_privileged"},
}

allowed_filesystems := {"readonly", "workspace", "temp"}

allow {
  role := input.agent.role
  role_max_risk[role]
  risk_rank[input.tool.risk_level] <= role_max_risk[role]
  profile := input.execution.profile
  role_profiles[role][profile]
  not input.execution.docker_socket
  allowed_filesystems[input.execution.filesystem]
}

deny_reason[msg] {
  input.execution.docker_socket
  msg := "docker socket access is forbidden"
}

deny_reason[msg] {
  role := input.agent.role
  role_max_risk[role]
  risk_rank[input.tool.risk_level] > role_max_risk[role]
  msg := "tool risk exceeds role limit"
}

deny_reason[msg] {
  role := input.agent.role
  profile := input.execution.profile
  not role_profiles[role][profile]
  msg := "execution profile not allowed for role"
}

deny_reason[msg] {
  not allowed_filesystems[input.execution.filesystem]
  msg := "filesystem profile not allowed"
}

reason := deny_reason
