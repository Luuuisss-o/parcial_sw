allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}
// vosk_flutter_2 es un plugin viejo: no declara `namespace` (AGP 8+ lo exige) y
// compila contra android-33 (sus dependencias androidx piden 34+). Lo corregimos
// desde acá en vez de editar la caché de pub. No cambia minSdk ni targetSdk.
subprojects {
    plugins.withId("com.android.library") {
        extensions.getByType(com.android.build.api.variant.LibraryAndroidComponentsExtension::class.java)
            .finalizeDsl { android ->
                if (android.namespace == null) {
                    android.namespace = when (project.name) {
                        "vosk_flutter_2" -> "org.vosk.vosk_flutter"
                        else -> project.group.toString()
                    }
                }
                if (project.name == "vosk_flutter_2") {
                    android.compileSdk = 36
                }
            }
    }
}
subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
