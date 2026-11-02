// Stub for non-web platforms.

void promptPwaInstall() {}

void openWebUrl(String url) {}

void downloadFile(List<int> bytes, String filename) {}

bool isPwaInstallSupported() => false;

bool isIosWeb() => false;

void forceAppUpdate() {}

bool isAppUpdateAvailable() => false;

void onAppUpdateAvailable(void Function() callback) {}

String? getAppBuildNumber() => null;

