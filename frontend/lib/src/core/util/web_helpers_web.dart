// ignore_for_file: deprecated_member_use, avoid_web_libraries_in_flutter
import 'dart:html' as html;
import 'dart:js' as js;

void promptPwaInstall() {
  try {
    js.context.callMethod('promptPwaInstall');
  } catch (_) {}
}

void openWebUrl(String url) {
  try {
    html.window.open(url, '_blank');
  } catch (_) {}
}

void downloadFile(List<int> bytes, String filename) {
  try {
    final blob = html.Blob([bytes]);
    final url = html.Url.createObjectUrlFromBlob(blob);
    html.AnchorElement(href: url)
      ..setAttribute('download', filename)
      ..click();
    html.Url.revokeObjectUrl(url);
  } catch (_) {}
}

bool isPwaInstallSupported() {
  try {
    return js.context['isPwaInstallAvailable'] == true;
  } catch (_) {
    return false;
  }
}

bool isIosWeb() {
  try {
    final ua = html.window.navigator.userAgent.toLowerCase();
    final isIos = ua.contains('iphone') || ua.contains('ipad') || ua.contains('ipod');
    final isIpadOs = ua.contains('macintosh') && (html.window.navigator.maxTouchPoints ?? 0) > 1;
    return isIos || isIpadOs;
  } catch (_) {
    return false;
  }
}

void forceAppUpdate() {
  try {
    js.context.callMethod('forceAppUpdate');
  } catch (_) {
    html.window.location.reload();
  }
}

bool isAppUpdateAvailable() {
  try {
    return js.context['isAppUpdateAvailable'] == true;
  } catch (_) {
    return false;
  }
}

String? getAppBuildNumber() {
  try {
    final build = js.context['appCurrentBuild'];
    if (build != null) return build.toString();
  } catch (_) {}
  return null;
}

void onAppUpdateAvailable(void Function() callback) {
  try {
    html.window.addEventListener('app-update-available', (_) {
      callback();
    });
  } catch (_) {}
}

