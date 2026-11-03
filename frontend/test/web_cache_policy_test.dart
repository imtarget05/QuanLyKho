import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('web release compares the running build with an uncached version marker', () {
    final index = File('web/index.html').readAsStringSync();
    final pagesHeaders = File('web/_headers').readAsStringSync();

    expect(index, contains('name="app-build-number"'));
    expect(index, contains("window.appCurrentBuild"));
    expect(index, contains("fetch('/version.json?_t=' + Date.now(), { cache: 'no-store' })"));
    expect(pagesHeaders, contains('/version.json'));
    expect(pagesHeaders, contains('Cache-Control: no-cache, no-store, must-revalidate'));
  });

  test('Nginx revalidates the app shell and only makes fingerprinted files immutable', () {
    final nginx = File('nginx.conf').readAsStringSync();

    for (final entrypoint in [
      '/index.html',
      '/version.json',
      '/flutter_service_worker.js',
      '/flutter_bootstrap.js',
      '/main.dart.js',
    ]) {
      expect(nginx, contains('location = $entrypoint'));
    }

    expect(nginx, contains('no-cache, no-store, must-revalidate'));
    expect(nginx, contains(r'\.[0-9a-f]{8,}\.'));
    expect(nginx, isNot(contains('expires 1y;')));
  });

  test('Cloudflare and Docker builds embed the matching release identifier', () {
    final pagesWorkflow =
        File('../.github/workflows/deploy-pages.yml').readAsStringSync();
    final dockerfile = File('Dockerfile').readAsStringSync();

    expect(pagesWorkflow, contains('__APP_BUILD_NUMBER__'));
    expect(dockerfile, contains('APP_BUILD_NUMBER'));
  });

  test('app update cleanup does not delete user-owned offline data', () {
    final index = File('web/index.html').readAsStringSync();

    expect(index, contains('caches.delete(key)'));
    expect(index, contains('r.unregister()'));
    expect(index, isNot(contains('localStorage.clear()')));
    expect(index, isNot(contains('indexedDB.deleteDatabase')));
  });
}
