terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.16"
    }
  }

  required_version = ">= 1.2.0"
}

provider "aws" {
  region  = "us-west-2"
}

data "aws_caller_identity" "current" {}

locals {
  account_id    = data.aws_caller_identity.current.account_id
  ecr_image_tag = "latest"
  iambic_public_repo = "public.ecr.aws/s2p9s3r8/iambic"
  iambic_image_tag = "latest"
}

resource "aws_ecr_repository" "iambic_private_ecr" {
  name                 = "iambic_private_ecr"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

/*
  provisioner "local-exec" {
    command = <<EOF
        aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin ${local.account_id}.dkr.ecr.us-west-2.amazonaws.com
        docker pull ${local.iambic_public_repo}:${local.iambic_image_tag}
        docker tag ${local.iambic_public_repo}:${local.iambic_image_tag} ${aws_ecr_repository.iambic_private_ecr.repository_url}:${local.ecr_image_tag}
        docker push ${aws_ecr_repository.iambic_private_ecr.repository_url}:${local.ecr_image_tag}

    EOF
  }*/
}

data "aws_ecr_image" "iambic_private_ecr" {
  repository_name = aws_ecr_repository.iambic_private_ecr.name
  image_tag       = "${local.ecr_image_tag}"
}

data "aws_iam_role" "iambic_github_app_lambda_execution" {
  name = "iambic_github_app_lambda_execution"
}


resource "aws_lambda_function" "iambic_github_app" {
  image_uri     = "${aws_ecr_repository.iambic_private_ecr.repository_url}:latest"  # repo and tag
  package_type  = "Image"
  function_name = "iambic_github_app_webhook"
  role          = data.aws_iam_role.iambic_github_app_lambda_execution.arn
  timeout       = 900

  source_code_hash = trimprefix(data.aws_ecr_image.iambic_private_ecr.id, "sha256:")

  image_config {
    command = ["iambic.cicd.github_app.run_handler"]
  }

  depends_on = [
    data.aws_iam_role.iambic_github_app_lambda_execution,
    aws_ecr_repository.iambic_private_ecr,
  ]
}

resource "aws_lambda_function_url" "iambic_github_app" {
  function_name      = aws_lambda_function.iambic_github_app.function_name
  authorization_type = "NONE"
}
