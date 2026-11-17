# Multi-Cloud Evidence — QuanLyKho (Azure)

Mục tiêu: chứng minh khả năng triển khai workload lên Azure qua Terraform + Azure CLI.

## 1. Thông tin Azure CLI

| Mục | Giá trị |
|-----|---------|
| Subscription | Azure subscription 1 (`a3deec78-7edb-41cd-9e94-ec1d4d9379f5`) |
| Tenant | `aa79a92c-ec09-4de1-baa9-151b8f9df886` (`binhtan5734gmail.onmicrosoft.com`) |
| User | `binhtan5734@gmail.com` |
| Azure CLI | 2.90.0 |

## 2. Infrastructure đã tạo trên Azure

| Resource | Tên | Vùng | SKU / Kích thước | Trạng thái | Cách tạo |
|----------|-----|------|------------------|------------|----------|
| Resource Group | `rg-bankops-eastus` | eastus | — | Succeeded | Terraform apply |
| Virtual Network | `vnet-rg-bankops-eastus` | eastus | — | Succeeded | Terraform apply |
| Subnet | `aks-subnet` | eastus | 10.0.1.0/24 | Succeeded | Terraform apply |
| Storage Account | `bankopseaststore` | eastus | Standard_LRS | Succeeded | Terraform apply |
| Storage Container | `backups` | eastus | — | Succeeded | Terraform apply |
| Key Vault | `kv-rg-bankops-eastus` | eastus | standard | Succeeded | Terraform apply |
| Log Analytics | `law-rg-bankops-eastus` | eastus | — | Succeeded | Terraform apply |
| Redis Cache | `redis-rg-bankops-eastus` | eastus | Basic | Succeeded | Terraform apply |
| AKS Cluster | `aks-rg-bankops-eastus` | eastus | 1 node, Standard_D2s_v4, K8s v1.36.5 | Succeeded | Azure CLI (`az aks create`) |

## 3. Các vấn đề gặp phải

| Vấn đề | Nguyên nhân | Hành động |
|--------|-------------|-----------|
| AWS provider credentials | Chưa cấu hình AWS | Bỏ qua, chỉ dùng Azure |
| Google provider credentials | Chưa cấu hình GCP | Bỏ qua, chỉ dùng Azure |
| PostgreSQL Flexible Server SKU | Tất cả SKU thử (Standard_B1ms, B2s, B4ms, D2s_v3) đều bị từ chối ở azurerm 3.102.0 | Bỏ qua PostgreSQL, sẽ dùng Azure Database for PostgreSQL Flexible Server qua Azure CLI sau nếu cần |
| AKS qua Terraform azurerm | API version `2023-06-02-preview` không được hỗ trợ | Tạo qua Azure CLI `az aks create` |
| VM size Standard_D2s_v3 | Không có trong subscription (eastus & southeastasia) | Dùng `Standard_D2s_v4` qua Azure CLI |

## 4. Evidence files

| File | Mô tả |
|------|-------|
| `docs/evidence/azure-resources-2026-11-14.json` | Danh sách tất cả resource trong RG |
| `docs/evidence/kubectl-nodes-2026-11-14.txt` | `kubectl get nodes -o wide` và `kubectl get pods --all-namespaces` |
| `docs/evidence/azure-terraform-plan-2026-11-14.txt` | Terraform plan output (read-only, trước khi apply) |

## 5. Cách lấy thêm evidence

```bash
# AKS cluster info
az aks show --resource-group rg-bankops-eastus --name aks-rg-bankops-eastus

# kubectl nodes
kubectl get nodes -o wide

# kubectl pods
kubectl get pods --all-namespaces

# Storage account keys
az storage account keys list --resource-group rg-bankops-eastus --account-name bankopseaststore

# Key Vault URI
az keyvault show --resource-group rg-bankops-eastus --name kv-rg-bankops-eastus --query properties.vaultUri
```

## 6. Multi-cloud (AWS/GCP)

Cần cấu hình credentials AWS/GCP nếu muốn chứng minh multi-cloud. Hiện chỉ chạy trên Azure.