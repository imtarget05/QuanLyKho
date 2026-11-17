# ── Multi-cloud: AWS ECS cluster (cross-cloud deploy evidence) ──────────────────
# Provisioned on AWS ap-southeast-1 to demonstrate cloud-agnostic deployment
# of the same workload that runs on Azure AKS.

resource "aws_vpc" "bankops_multi" {
  provider = aws.multi_cloud

  cidr_block = "10.1.0.0/16"
  tags = merge(var.common_tags, {
    provider = "aws"
    purpose  = "multi-cloud-evidence"
  })
}

resource "aws_subnet" "bankops_multi" {
  provider = aws.multi_cloud

  vpc_id     = aws_vpc.bankops_multi.id
  cidr_block = "10.1.1.0/24"
  tags = merge(var.common_tags, {
    provider = "aws"
    purpose  = "multi-cloud-evidence"
  })
}

resource "aws_ecs_cluster" "bankops_multi" {
  provider = aws.multi_cloud

  name = "bankops-multi-cluster"
  tags = merge(var.common_tags, {
    provider = "aws"
    purpose  = "multi-cloud-evidence"
  })
}

resource "aws_ecs_service" "bankops_api" {
  provider = aws.multi_cloud

  name            = "bankops-api"
  cluster         = aws_ecs_cluster.bankops_multi.id
  task_definition = ""  # Populated by CI/CD pipeline with built image
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = [aws_subnet.bankops_multi.id]
    security_groups = []
    assign_public_ip = true
  }

  tags = merge(var.common_tags, {
    provider = "aws"
    purpose  = "multi-cloud-evidence"
  })
}

# ── Multi-cloud: GCP Cloud Run service (cross-cloud deploy evidence) ────────────
# Provisioned on GCP asia-southeast1 to demonstrate cloud-agnostic deployment
# of the same workload that runs on Azure AKS.

resource "google_cloud_run_service" "bankops_api" {
  provider = google.multi_cloud

  name     = "bankops-api"
  location = var.gcp_region

  template {
    spec {
      containers {
        image = "ghcr.io/imtarget05/bankops-api:latest"  # Overridden by CI/CD
        env {
          name  = "APP_ENV"
          value = "production"
        }
        env {
          name  = "DEMO_MODE"
          value = "false"
        }
        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }
}

# ── Outputs for multi-cloud evidence ─────────────────────────────────────────────
output "aws_ecs_cluster_name" {
  value     = aws_ecs_cluster.bankops_multi.name
  sensitive = false
}

output "gcp_cloud_run_service_name" {
  value     = google_cloud_run_service.bankops_api.name
  sensitive = false
}

output "gcp_cloud_run_service_url" {
  value     = google_cloud_run_service.bankops_api.status.0.url
  sensitive = false
}