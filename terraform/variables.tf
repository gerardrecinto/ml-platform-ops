variable "region" {
  type    = string
  default = "us-west-2"
}

variable "name" {
  type    = string
  default = "mlplat"
}

variable "vpc_id" {
  type        = string
  description = "Existing VPC. This config does not create networking."
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnets for nodes and the control plane."
}

variable "node_instance_types" {
  type    = list(string)
  default = ["m6i.large"]
}

variable "node_min" {
  type    = number
  default = 2
}

variable "node_max" {
  type    = number
  default = 6
}

variable "alarm_topic_arn" {
  type        = string
  description = "SNS topic that receives the node alarm."
}
