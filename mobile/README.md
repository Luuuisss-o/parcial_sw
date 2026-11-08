# UML Collab Mobile

App Flutter con el mismo backend FastAPI del editor web, más un asistente
de edición por voz o texto que corre **100% offline** en el teléfono:
reconocimiento de voz con Vosk y un LLM chico (Gemma 3 1B IT cuantizado,
empaquetado dentro del propio APK) corriendo con llama.cpp vía `llamadart`.

Además, la app puede conectarse a **cualquier backend Spring Boot generado
por el diagramador** (protocolo UAP, ver `lib/uap/`) y usar el mismo
asistente de voz/texto para operar sus datos, sin conocer su dominio de
antemano -- ver sección 9.

## 1. Instalar herramientas (una vez)

1. Java 17 (Temurin).
2. Android SDK, solo *command line tools*:
   - Descargar "Command line tools only" desde https://developer.android.com/studio#command-tools
   - Descomprimir en, por ejemplo, `C:\Android\cmdline-tools\latest\`
   - Variables de entorno: `ANDROID_HOME=C:\Android`, y agregar al `PATH`:
     `%ANDROID_HOME%\cmdline-tools\latest\bin` y `%ANDROID_HOME%\platform-tools`
   - `sdkmanager --licenses`
   - `sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0"`
3. Flutter SDK: https://docs.flutter.dev/get-started/install/windows
4. Verificar todo con:

```bash
flutter doctor
```

## 2. Generar el proyecto Android (una vez)

Este repo trae solo el código Dart (`lib/`) y `pubspec.yaml`. Falta la carpeta
`android/` con el proyecto Gradle, que Flutter genera automáticamente:

```bash
cd mobile
flutter create --platforms=android --org com.parcialsw --project-name uml_collab_mobile .
```

Esto NO pisa `lib/` ni `pubspec.yaml` (ya existen), solo agrega `android/`.

## 3. Ajustes en `android/app/src/main/AndroidManifest.xml`

Agregar el permiso de micrófono (necesario para Vosk) dentro de `<manifest>`,
antes de `<application>`:

```xml
<uses-permission android:name="android.permission.RECORD_AUDIO" />
<uses-permission android:name="android.permission.INTERNET" />
```

## 4. Ajustar `minSdkVersion`

En `android/app/build.gradle` (o `build.gradle.kts`), dentro de `defaultConfig`,
asegurar `minSdk = 24` (lo pide `llamadart` para el runtime nativo de
llama.cpp; el default de Flutter ya suele ser suficiente, pero conviene
confirmarlo):

```gradle
defaultConfig {
    minSdkVersion 24
    ...
}
```

## 5. Instalar dependencias

```bash
flutter pub get
```

## 6. Probar en el teléfono físico (recomendado, en vez de emulador)

1. Activar "Opciones de desarrollador" y "Depuración USB" en el Xiaomi.
2. Conectar por USB y confirmar el diálogo de autorización en el teléfono.
3. Verificar que aparece:

```bash
flutter devices
```

4. Instalar y correr:

```bash
flutter run
```

Cada `flutter run` reinstala el APK actualizado en el teléfono conectado.

## 7. Backend

Por defecto la app apunta a `http://10.0.2.2:8000` (`lib/config.dart`), que
es la dirección especial del emulador Android hacia el `localhost` de la PC.
Para un teléfono físico por USB, dos opciones:

- **Más simple:** cambiar `apiBaseUrl` en `lib/config.dart` por la IP local
  de la PC en la red WiFi (ej. `http://192.168.1.50:8000`), con el teléfono
  en la misma red.
- **Alternativa por cable:** `adb reverse tcp:8000 tcp:8000` y dejar
  `http://localhost:8000` (redirige el puerto del teléfono al de la PC).

## 8. Modelo local (Gemma 3 1B)

El LLM del asistente va **empaquetado dentro del APK** (no se descarga en
runtime como el modelo de voz de Vosk), porque es la pieza fija del
sistema: un solo modelo, para cualquier backend al que la app se conecte
después.

**Antes de compilar** (`flutter build apk` / `flutter run`), hay que
descargar el archivo manualmente y colocarlo en:

```
mobile/assets/models/assistant.gguf
```

No se versiona en git (ver `.gitignore`) porque pesa demasiado para un
repo normal.

| | |
|---|---|
| **Modelo** | Gemma 3 1B IT (instruction-tuned), cuantizado GGUF Q4_K_M |
| **Tamaño aproximado** | ~700–900 MB (varía según la cuantización exacta que se descargue) |
| **Licencia** | [Gemma Terms of Use](https://ai.google.dev/gemma/terms) de Google -- uso permitido incluyendo comercial, con restricciones de uso responsable (prohíbe usos dañinos listados en la Prohibited Use Policy de Gemma); no es una licencia OSI-aprobada tipo MIT/Apache, es una licencia propia de Google para este modelo |
| **Fuente de descarga** | Hugging Face, ej. repos de cuantizaciones GGUF de Gemma 3 1B IT (buscar "gemma-3-1b-it GGUF"); verificar que el archivo sea la variante `Q4_K_M` |
| **Requisitos de almacenamiento** | El .gguf en assets (~700-900 MB) + su copia en almacenamiento privado de la app tras el primer arranque (`ensureLlmModel()`, ver `model_downloader.dart`) -- calcular ~1.5-1.8 GB libres en el dispositivo durante ese primer arranque |
| **Consumo de memoria (RAM)** | Aproximadamente el tamaño del modelo cargado (~700-900 MB) más el buffer de contexto de inferencia -- un modelo de 1B es notablemente más liviano en RAM que Qwen 1.5B (el que se usaba antes) |
| **Rendimiento esperado (Snapdragon 720G)** | Referencial, sin medición propia: un modelo de 1B parámetros cuantizado a Q4_K_M suele generar en el orden de unos pocos tokens por segundo en un SoC de esa gama (720G es de 2020, sin NPU dedicada para LLMs) -- suficiente para las respuestas cortas de tool-calling que este asistente necesita (~200 tokens máx), pero notablemente más lento que un modelo cloud. **No verificado en un dispositivo real en esta sesión.** |
| **Inferencia** | 100% local, vía `llamadart` (bindings de llama.cpp) -- nunca se manda el texto del usuario a ningún servicio externo |
| **Primera compilación** | Puede necesitar internet para que `llamadart`/Flutter descarguen el runtime nativo de llama.cpp (binarios prebuilt del paquete), además de la descarga manual del .gguf mencionada arriba |
| **Uso posterior** | Una vez compilado el APK con el modelo embebido, la generación de texto funciona **completamente offline** -- no requiere red salvo para hablar con el backend (diagramador o backend UAP generado), que es un tema aparte de la inferencia del LLM |

El modelo de voz en español de Vosk (~50 MB) sigue descargándose en
runtime, la primera vez que se abre el asistente -- pesa poco comparado
con el LLM y no justifica inflar el APK.

## 9. Conectarse a un backend Spring Boot generado (protocolo UAP)

Además del flujo del diagramador (arriba), la app puede conectarse a
**cualquier** backend Spring Boot exportado por el diagramador ese día
(dominio arbitrario, definido por el diagrama con el que se generó) y
ofrecer el mismo asistente para operar sus datos. Ver `lib/uap/` para el
cliente/parser/descubrimiento, y `lib/db/` para la persistencia offline.

Configurar la URL del backend generado en `lib/uap/uap_config.dart`
(o vía `--dart-define` en build time):

```bash
flutter run \
  --dart-define=UAP_DEPLOYED_URL=http://192.168.0.10:8090 \
  --dart-define=UAP_USB_URL=http://127.0.0.1:8090 \
  --dart-define=UAP_HOST_HEADER=localhost:8090
```

Para conectar por USB (sin WiFi compartida), correr una vez con el cable
conectado:

```bash
adb reverse tcp:8090 tcp:8090
```

Desde la app: pantalla "¿Qué querés hacer?" → "Usar un sistema generado" →
elegir USB o WiFi/LAN → Conectar. La app descubre las entidades y
operaciones disponibles automáticamente (no hace falta programar nada
específico para ese backend).
