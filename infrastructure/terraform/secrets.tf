resource "aws_secretsmanager_secret" "openai" {
  name                    = "${local.prefix}/openai_api_key"
  recovery_window_in_days = 0
  tags                    = local.common_tags
}

resource "aws_secretsmanager_secret_version" "openai" {
  secret_id     = aws_secretsmanager_secret.openai.id
  secret_string = var.openai_api_key
}

resource "aws_secretsmanager_secret" "gemini" {
  name                    = "${local.prefix}/gemini_api_key"
  recovery_window_in_days = 0
  tags                    = local.common_tags
}

resource "aws_secretsmanager_secret_version" "gemini" {
  secret_id     = aws_secretsmanager_secret.gemini.id
  secret_string = var.gemini_api_key
}

resource "aws_secretsmanager_secret" "db_password" {
  name                    = "${local.prefix}/db_password"
  recovery_window_in_days = 0
  tags                    = local.common_tags
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = var.db_password
}

resource "aws_secretsmanager_secret" "initial_admin_key" {
  name                    = "${local.prefix}/initial_admin_key"
  recovery_window_in_days = 0
  tags                    = local.common_tags
}

resource "aws_secretsmanager_secret_version" "initial_admin_key" {
  secret_id     = aws_secretsmanager_secret.initial_admin_key.id
  secret_string = var.initial_admin_key
}
