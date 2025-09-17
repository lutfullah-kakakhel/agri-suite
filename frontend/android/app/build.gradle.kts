plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.doordars.agroassist"         // TODO: your package
    compileSdk = 36

    defaultConfig {
        applicationId = "com.doordars.agroassist"  // TODO: your package
        minSdk = flutter.minSdkVersion
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            // ✅ Fix: enable code shrink + resource shrink
            isMinifyEnabled = true
            isShrinkResources = true

            // Keep defaults; add your own rules in proguard-rules.pro if needed
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
        debug {
            // Leave shrinking off for debug
            isMinifyEnabled = false
            isShrinkResources = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    // Add Android deps here if needed
}
