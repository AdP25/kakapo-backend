output "alb_dns_name" {
  description = "Public URL of the API — share this link"
  value       = "http://${aws_lb.main.dns_name}"
}

output "ecr_repository_url" {
  description = "ECR URL — use this when pushing your Docker image"
  value       = aws_ecr_repository.api.repository_url
}

output "database_url" {
  description = "DATABASE_URL to set in ECS task env (asyncpg)"
  value       = "postgresql+asyncpg://kakapo:${var.db_password}@${aws_db_instance.postgres.address}:5432/kakapo"
  sensitive   = true
}

output "redis_url" {
  description = "REDIS_URL to set in ECS task env"
  value       = "redis://${aws_elasticache_cluster.redis.cache_nodes[0].address}:6379"
}

output "rds_endpoint" {
  value = aws_db_instance.postgres.address
}

output "redis_endpoint" {
  value = aws_elasticache_cluster.redis.cache_nodes[0].address
}
