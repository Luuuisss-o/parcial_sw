# R8 (activo por defecto en release) renombraba las clases de JNA, que usa
# Vosk (vosk_flutter_2) para el reconocimiento de voz. El código nativo de
# JNA busca campos por nombre (ej. com.sun.jna.Pointer.peer) y la app se
# cerraba con "UnsatisfiedLinkError: Can't obtain peer field ID".
-keep class com.sun.jna.** { *; }
-keepclassmembers class * extends com.sun.jna.** { public *; }
-keep class org.vosk.** { *; }
-dontwarn java.awt.**
-dontwarn com.sun.jna.**
