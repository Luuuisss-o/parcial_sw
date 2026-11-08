// lib/uap/uap_config.dart
//
// Configuración de conexión al backend Spring Boot GENERADO por el
// diagramador (no confundir con lib/config.dart, que apunta al backend
// FastAPI del diagramador en sí -- son dos backends distintos, ver
// uap_client.dart). El backend generado no tiene una URL fija: se genera
// de nuevo cada vez que alguien exporta un diagrama, típicamente el mismo
// día del examen, así que esto tiene que poder cambiarse fácil sin
// recompilar toda la lógica de la app.
//
// Dos formas de llegar a él desde el celular:
// - LAN/WiFi: la PC y el teléfono están en la misma red, se usa la IP de
//   la PC directamente (deployedBackendUrl).
// - USB: se corre `adb reverse tcp:<puerto> tcp:<puerto>` una vez con el
//   cable conectado, y el teléfono habla contra 127.0.0.1 como si el
//   backend corriera en el propio teléfono -- útil cuando no hay WiFi
//   compartida disponible el día del examen. El backend puede filtrar por
//   header Host (algunos setups de reverse proxy lo hacen); por eso se
//   manda explícito en vez de confiar en lo que adb reverse deja como Host
//   real (que sería "127.0.0.1", no necesariamente el que el backend
//   espera).

enum UapConnectionMode { usb, deployed }

class UapConfig {
  /// Backend desplegado en la LAN/WiFi. Cambiar por la IP real de la PC
  /// que corre `docker compose up` del proyecto exportado (puerto 8090,
  /// ver exporters/templates/docker-compose.yml.j2).
  static const String deployedBackendUrl = String.fromEnvironment(
    'UAP_DEPLOYED_URL',
    defaultValue: 'http://192.168.0.10:8090',
  );

  /// Con el celular por USB y `adb reverse tcp:8090 tcp:8090` corrido una
  /// vez, el puerto 8090 del teléfono queda reenviado al 8090 de la PC:
  /// la app entonces habla contra 127.0.0.1 como si el backend estuviera
  /// en el propio dispositivo.
  static const String usbBackendUrl = String.fromEnvironment(
    'UAP_USB_URL',
    defaultValue: 'http://127.0.0.1:8090',
  );

  /// Header Host a mandar explícito cuando se usa el modo USB. Con
  /// `adb reverse`, el Host real de la conexión sería "127.0.0.1:8090",
  /// que puede no ser el que el backend (o un proxy delante) espera --
  /// se manda el que corresponde en vez de confiar en el que arma el
  /// stack de red del teléfono.
  static const String backendHostHeader = String.fromEnvironment(
    'UAP_HOST_HEADER',
    defaultValue: 'localhost:8090',
  );
}

/// Resuelve la URL efectiva y los headers extra según el modo de conexión
/// elegido. Clase separada (no solo funciones sueltas) para que
/// UapConnectScreen pueda guardar "cuál modo está activo" como un solo
/// valor y no tener que repetir el switch en cada lugar que arma una
/// petición.
class UapEndpoint {
  final UapConnectionMode mode;

  const UapEndpoint(this.mode);

  String get baseUrl {
    switch (mode) {
      case UapConnectionMode.usb:
        return UapConfig.usbBackendUrl;
      case UapConnectionMode.deployed:
        return UapConfig.deployedBackendUrl;
    }
  }

  /// Headers que hay que agregar a TODA petición contra este endpoint,
  /// además de los que arme cada llamada puntual (Content-Type, etc).
  /// Solo el modo USB necesita el header Host explícito.
  Map<String, String> get extraHeaders {
    switch (mode) {
      case UapConnectionMode.usb:
        return {'Host': UapConfig.backendHostHeader};
      case UapConnectionMode.deployed:
        return const {};
    }
  }
}
