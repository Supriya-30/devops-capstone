# README Phase 5: VPC + EKS using battle-tested official modules.
# WARNING: EKS costs real money (~$0.10/hr control plane + nodes). ALWAYS run
# `terraform destroy` when finished.
#
# Usage:
#   terraform init
#   terraform plan        # review like a release note — know what changes before it changes
#   terraform apply
#   aws eks update-kubeconfig --name devops-capstone-eks --region ap-south-1
#   terraform destroy     # when done!

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  # Team best practice — remote state with locking (uncomment and create the bucket/table first):
  # backend "s3" {
  #   bucket         = "my-terraform-state-bucket"
  #   key            = "devops-capstone/terraform.tfstate"
  #   region         = "ap-south-1"
  #   dynamodb_table = "terraform-locks"
  # }
}

provider "aws" {
  region = var.region
}

variable "region" {
  type    = string
  default = "ap-south-1"
}

variable "cluster_name" {
  type    = string
  default = "devops-capstone-eks"
}

data "aws_availability_zones" "available" {
  state = "available"
}

# ---------------- VPC (official module) ----------------
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.8"

  name = "devops-capstone-vpc"
  cidr = "10.0.0.0/16"

  azs             = slice(data.aws_availability_zones.available.names, 0, 2)
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"] # worker nodes live here (not internet-facing)
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24"]

  enable_nat_gateway   = true  # private subnets reach the internet outbound (image pulls)
  single_nat_gateway   = true  # one NAT to keep the demo bill low
  enable_dns_hostnames = true

  # Tags required for Kubernetes load balancer integration
  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
  }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
  }
}

# ---------------- EKS (official module) ----------------
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.8"

  cluster_name    = var.cluster_name
  cluster_version = "1.30"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets # nodes in private subnets = security best practice

  cluster_endpoint_public_access = true # so you and GitHub Actions can reach the API server

  # Give the user who runs `terraform apply` admin access to the cluster
  enable_cluster_creator_admin_permissions = true

  eks_managed_node_groups = {
    default = {
      instance_types = ["t3.medium"] # smallest size that runs EKS system pods comfortably
      min_size       = 1
      max_size       = 3
      desired_size   = 2
    }
  }
}

output "cluster_name" {
  value = module.eks.cluster_name
}

output "configure_kubectl" {
  value = "aws eks update-kubeconfig --name ${module.eks.cluster_name} --region ${var.region}"
}
