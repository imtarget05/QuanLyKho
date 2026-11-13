# Helpers for the quanlykho chart.

{{/* Chart name (chart name only). */}}
{{- define "quanlykho.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Fully qualified object name: release-name-chartname (or fullnameOverride). */}}
{{- define "quanlykho.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/* Chart name + version labels. */}}
{{- define "quanlykho.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Common labels. */}}
{{- define "quanlykho.labels" -}}
helm.sh/chart: {{ include "quanlykho.chart" . }}
{{ include "quanlykho.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: quanlykho-system
{{- end -}}

{{/* Selector labels (immutable for Deployment selectors). */}}
{{- define "quanlykho.selectorLabels" -}}
app.kubernetes.io/name: {{ include "quanlykho.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* Service account name. */}}
{{- define "quanlykho.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "quanlykho.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/* External Secret name used by envFrom secretRef. */}}
{{- define "quanlykho.secretName" -}}
{{- .Values.secrets.existingSecret | required "secrets.existingSecret is required" -}}
{{- end -}}
