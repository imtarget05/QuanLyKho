import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('web release compares the running build with an uncached version marker',
      () {
    final index = File('web/index.html').readAsStringSync();
    final webHeaders = File('web/_headers').readAsStringSync();
    final deployedHeaders =
        File('../infra/cloudflare-pages/_headers').readAsStringSync();

    expect(index, contains('name="app-build-number"'));
    expect(index, contains("window.appCurrentBuild"));
    expect(
        index,
        contains(
            "fetch('/version.json?_t=' + Date.now(), { cache: 'no-store' })"));
    for (final headers in [webHeaders, deployedHeaders]) {
      expect(headers, contains('/version.json'));
      expect(headers,
          contains('Cache-Control: no-cache, no-store, must-revalidate'));
      expect(headers,
          contains('/assets/*\n  Cache-Control: no-cache, must-revalidate'));
      expect(headers,
          contains('/canvaskit/*\n  Cache-Control: no-cache, must-revalidate'));
      expect(headers, isNot(contains('max-age=31536000, immutable')));
    }
  });

  test(
      'Nginx revalidates the app shell and only makes fingerprinted files immutable',
      () {
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
    final immutableRule = RegExp(
      r'location ~\* \\\.\[0-9a-f\]\{8,\}\\\.\(\?:[^)]*\)\$ \{([^}]*)\}',
      dotAll: true,
    ).firstMatch(nginx);
    expect(immutableRule, isNotNull);
    expect(immutableRule!.group(1), contains('expires 1y;'));
    expect(immutableRule.group(1), contains('immutable'));
  });

  test('Cloudflare and Docker builds embed the matching release identifier',
      () {
    final pagesWorkflow =
        File('../.github/workflows/deploy-pages.yml').readAsStringSync();
    final dockerfile = File('Dockerfile').readAsStringSync();

    expect(pagesWorkflow, contains('__APP_BUILD_NUMBER__'));
    expect(dockerfile, contains('APP_BUILD_NUMBER'));
    expect(
      pagesWorkflow,
      contains(
          'cp infra/cloudflare-pages/_headers frontend/build/worker-assets/_headers'),
    );
  });

  test('app update cleanup does not delete user-owned offline data', () {
    final index = File('web/index.html').readAsStringSync();

    expect(index, contains('caches.delete(key)'));
    expect(index, contains('r.unregister()'));
    expect(index, isNot(contains('localStorage.clear()')));
    expect(index, isNot(contains('indexedDB.deleteDatabase')));
  });
}
