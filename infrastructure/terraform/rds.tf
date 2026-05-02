resource "aws_db_subnet_group" "main" {
  name       = "${local.prefix}-db-subnet"
  subnet_ids = aws_subnet.private[*].id
  tags       = merge(local.common_tags, { Name = "${local.prefix}-db-subnet" })
}

resource "aws_db_instance" "postgres" {
  identifier        = "${local.prefix}-postgres"
  engine            = "postgres"
  engine_version    = "15.6"
  instance_class    = "db.t3.medium"
  allocated_storage = 20
  storage_type      = "gp3"

  db_name  = "kakapo"
  username = "kakapo"
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  # pgvector is installed via the app's CREATE EXTENSION at startup
  parameter_group_name = aws_db_parameter_group.postgres.name

  backup_retention_period = 7
  skip_final_snapshot     = var.environment != "prod"
  deletion_protection     = var.environment == "prod"
  multi_az                = var.environment == "prod"

  tags = merge(local.common_tags, { Name = "${local.prefix}-postgres" })
}

resource "aws_db_parameter_group" "postgres" {
  name   = "${local.prefix}-pg15"
  family = "postgres15"
  tags   = local.common_tags
}
