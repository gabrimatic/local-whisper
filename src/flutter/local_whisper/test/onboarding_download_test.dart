import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:local_whisper_flutter/src/app.dart';
import 'package:local_whisper_flutter/src/model_store.dart';
import 'package:local_whisper_flutter/src/models.dart';
import 'package:local_whisper_flutter/src/setup_service.dart';

void main() {
  testWidgets('alternate setup install shows progress, errors, and a retry for the same pack', (tester) async {
    tester.view.devicePixelRatio = 1.5;
    tester.view.physicalSize = const Size(1080, 2200);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);
    final defaultModel = ModelStore.catalog
        .firstWhere((model) => model.id == 'qwen3_asr_sherpa')
        .copyWith(state: ModelInstallState.installed);
    final fourier = ModelStore.catalog.firstWhere((model) => model.id == 'oruk_fourier_2b_sherpa');
    var alternate = fourier;
    late StateSetter update;
    var pending = Completer<String?>();
    final calls = <String>[];

    await tester.pumpWidget(MaterialApp(home: StatefulBuilder(
      builder: (context, setState) {
        update = setState;
        return OnboardingFlow(
          settings: AppSettings(selectedModelId: defaultModel.id),
          status: const NativeSpeechStatus.unknown(),
          keyboardStatus: const KeyboardSetupStatus.unknown(),
          models: [defaultModel, alternate],
          selectedModel: defaultModel,
          onRequestMicrophone: () {},
          onOpenKeyboardSettings: () {},
          onOpenAppSettings: () {},
          onRefreshKeyboardStatus: () {},
          onKeyboardPracticeVerified: () {},
          onFinish: () {},
          onDownloadModel: (model) {
            calls.add(model.id);
            return pending.future;
          },
        );
      },
    )));
    await tester.tap(find.text('Start setup'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('More choices'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(TextButton, 'Install'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 450));
    expect(calls, [fourier.id]);
    expect(find.text('Installing'), findsOneWidget);
    expect(find.text(fourier.name), findsOneWidget);
    expect(find.text('Recommended'), findsNothing);

    update(() => alternate = fourier.copyWith(
      state: ModelInstallState.downloading, installedBytes: 8 * 1024 * 1024, progress: .25,
    ));
    await tester.pump();
    expect(find.text('8.0 MiB downloaded'), findsOneWidget);
    expect(tester.widgetList<LinearProgressIndicator>(find.byType(LinearProgressIndicator)).any((bar) => bar.value == .25), isTrue);

    update(() => alternate = fourier);
    pending.complete('Network connection lost');
    await tester.pumpAndSettle();
    expect(find.text('Network connection lost'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
    expect(tester.widget<OnboardingFlow>(find.byType(OnboardingFlow)).selectedModel.id, defaultModel.id);
    expect(defaultModel.state, ModelInstallState.installed);

    pending = Completer<String?>();
    await tester.ensureVisible(find.text('Retry'));
    await tester.tap(find.text('Retry'));
    await tester.pump();
    expect(calls, [fourier.id, fourier.id]);
    expect(find.text('Network connection lost'), findsNothing);
    update(() => alternate = fourier.copyWith(state: ModelInstallState.installed));
    pending.complete(null);
    await tester.pumpAndSettle();
    expect(find.text('${fourier.name} is ready for offline transcription.'), findsOneWidget);
  });
}
