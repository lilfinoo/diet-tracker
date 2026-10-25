package fit.tracker.android

import android.Manifest
import android.content.ClipData
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.exifinterface.media.ExifInterface
import java.io.File
import java.io.IOException

object NativePhotoPlatform {
    private var sweptOldPhotos = false

    @Synchronized
    fun directory(context: Context): File {
        val directory = File(context.cacheDir, "fit-tracker-photos")
        if ((!directory.exists() && !directory.mkdirs()) || !directory.isDirectory) throw IOException("Não foi possível preparar o armazenamento de fotos.")
        if (!sweptOldPhotos) {
            val cutoff = System.currentTimeMillis() - 24L * 60 * 60 * 1000
            directory.listFiles()?.filter { it.isFile && it.lastModified() < cutoff }?.forEach { it.delete() }
            sweptOldPhotos = true
        }
        return directory
    }

    private fun removeOwnedCapture(context: Context, uri: Uri) {
        if (uri.scheme != "file") return
        val file = File(uri.path ?: return)
        if (file.name.startsWith("fit-camera-") && file.canonicalFile.parentFile == directory(context).canonicalFile) file.delete()
    }

    fun discardCapture(context: Context, source: String) {
        removeOwnedCapture(context, Uri.parse(source))
    }

    @Composable
    fun Picker(camera: Boolean, completion: (String?, String?) -> Unit) {
        val context = LocalContext.current
        val captureFile = remember { mutableStateOf<File?>(null) }
        val cameraLauncher = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { success ->
            val file = captureFile.value
            if (!success) file?.delete()
            completion(if (success && file != null) Uri.fromFile(file).toString() else null, null)
        }
        val libraryLauncher = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
            completion(uri?.toString(), null)
        }
        fun capture() {
            try {
                val file = File.createTempFile("fit-camera-", ".jpg", directory(context))
                captureFile.value = file
                val uri = FileProvider.getUriForFile(context, context.packageName + ".fileprovider", file)
                cameraLauncher.launch(uri)
            } catch (error: Exception) {
                captureFile.value?.delete()
                completion(null, "A câmera não está disponível. Escolha uma foto na galeria.")
            }
        }
        val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) capture() else completion(null, "Permita o acesso à câmera nas configurações ou use a galeria.")
        }
        LaunchedEffect(camera) {
            if (camera) {
                if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                    capture()
                } else permissionLauncher.launch(Manifest.permission.CAMERA)
            } else {
                try { libraryLauncher.launch("image/*") }
                catch (error: Exception) { completion(null, "Não foi possível abrir a galeria neste aparelho.") }
            }
        }
    }

    // Sample while decoding, normalize EXIF orientation, then bound uploads to 1600 px.
    // The app never reads the entire photo library or writes to shared storage.
    fun prepare(context: Context, source: String): String {
        val uri = Uri.parse(source)
        try {
            val resolver = context.contentResolver
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            resolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) }
            if (bounds.outWidth <= 0 || bounds.outHeight <= 0) throw IOException("Imagem inválida.")
            var sample = 1
            while (maxOf(bounds.outWidth, bounds.outHeight) / sample > 3200) sample *= 2
            val options = BitmapFactory.Options().apply { inSampleSize = sample }
            var bitmap = resolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, options) }
            ?: throw IOException("Não foi possível abrir a imagem.")
            try {
                val orientation = resolver.openInputStream(uri)?.use {
                    ExifInterface(it).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
                } ?: ExifInterface.ORIENTATION_NORMAL
                val matrix = Matrix()
                when (orientation) {
                    ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> matrix.setScale(-1f, 1f)
                    ExifInterface.ORIENTATION_ROTATE_180 -> matrix.setRotate(180f)
                    ExifInterface.ORIENTATION_FLIP_VERTICAL -> matrix.setScale(1f, -1f)
                    ExifInterface.ORIENTATION_TRANSPOSE -> { matrix.setRotate(90f); matrix.postScale(-1f, 1f) }
                    ExifInterface.ORIENTATION_ROTATE_90 -> matrix.setRotate(90f)
                    ExifInterface.ORIENTATION_TRANSVERSE -> { matrix.setRotate(-90f); matrix.postScale(-1f, 1f) }
                    ExifInterface.ORIENTATION_ROTATE_270 -> matrix.setRotate(-90f)
                }
                if (!matrix.isIdentity) {
                    val rotated = Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
                    if (rotated !== bitmap) bitmap.recycle()
                    bitmap = rotated
                }
                val scale = minOf(1f, 1600f / maxOf(bitmap.width, bitmap.height))
                if (scale < 1f) {
                    val resized = Bitmap.createScaledBitmap(bitmap, maxOf(1, (bitmap.width * scale).toInt()), maxOf(1, (bitmap.height * scale).toInt()), true)
                    if (resized !== bitmap) bitmap.recycle()
                    bitmap = resized
                }
                val file = File.createTempFile("fit-photo-", ".jpg", directory(context))
                try {
                    file.outputStream().use { if (!bitmap.compress(Bitmap.CompressFormat.JPEG, 80, it)) throw IOException("Não foi possível preparar a foto.") }
                } catch (error: Exception) { file.delete(); throw error }
                return file.absolutePath
            } finally { bitmap.recycle() }
        } finally { removeOwnedCapture(context, uri) }
    }

    fun share(activity: AppCompatActivity, path: String) {
        val file = File(path)
        if (!file.isFile) throw IOException("A imagem não está mais disponível.")
        val uri = FileProvider.getUriForFile(activity, activity.packageName + ".fileprovider", file)
        val send = Intent(Intent.ACTION_SEND).apply {
            type = if (file.extension.equals("png", ignoreCase = true)) "image/png" else "image/jpeg"
            putExtra(Intent.EXTRA_STREAM, uri)
            clipData = ClipData.newRawUri("Fit Tracker", uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        activity.startActivity(Intent.createChooser(send, "Compartilhar imagem"))
    }

    fun renderMeal(context: Context, photoPath: String, title: String, calories: String, protein: String, carbs: String, fat: String, logoPath: String): String {
        val photo = BitmapFactory.decodeFile(photoPath) ?: throw IOException("Foto inválida.")
        val logo = BitmapFactory.decodeFile(logoPath) ?: run { photo.recycle(); throw IOException("Logo indisponível.") }
        val result = Bitmap.createBitmap(1080, 1920, Bitmap.Config.ARGB_8888)
        try {
            val canvas = Canvas(result)
            val paint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
            val scale = maxOf(1080f / photo.width, 1920f / photo.height)
            val left = (1080f - photo.width * scale) / 2
            val top = (1920f - photo.height * scale) / 2
            canvas.drawBitmap(photo, null, RectF(left, top, left + photo.width * scale, top + photo.height * scale), paint)
            val cyan = Color.rgb(0, 217, 237)
            val panel = RectF(48f, 1320f, 1032f, 1872f)
            paint.color = Color.argb(199, 4, 9, 17)
            canvas.drawRoundRect(panel, 42f, 42f, paint)
            paint.color = cyan; paint.alpha = 204; paint.style = Paint.Style.STROKE; paint.strokeWidth = 3f
            canvas.drawRoundRect(panel, 42f, 42f, paint)
            paint.style = Paint.Style.FILL; paint.alpha = 255
            fun text(value: String, x: Float, top: Float, size: Float, color: Int, bold: Boolean = true, width: Float = 888f) {
                paint.color = color
                paint.textSize = size
                paint.typeface = if (bold) Typeface.create("sans-serif", Typeface.BOLD) else Typeface.create("sans-serif", Typeface.NORMAL)
                while (paint.measureText(value) > width && paint.textSize > 16f) paint.textSize -= 1f
                canvas.drawText(value, x, top - paint.fontMetrics.ascent, paint)
            }
            paint.color = cyan
            canvas.drawRect(90f, 1452f, 96f, 1590f, paint)
            text(title, 90f, 1360f, if (title.length > 24) 42f else 54f, Color.WHITE, width = 740f)
            text(calories, 120f, 1428f, 128f, Color.WHITE)
            text("kcal estimadas", 120f, 1590f, 28f, Color.LTGRAY, false)
            val macros = listOf("PROTEÍNAS" to protein, "CARBOIDRATOS" to carbs, "GORDURAS" to fat).filter { it.second.isNotEmpty() }
            val column = 888f / maxOf(1, macros.size)
            macros.forEachIndexed { index, macro ->
                val x = 96f + index * column
                paint.color = if (macro.first == "CARBOIDRATOS") Color.rgb(0, 122, 255) else Color.rgb(0, 217, 191)
                canvas.drawRect(x, 1670f, x + 44f, 1675f, paint)
                text(macro.first, x, 1700f, 22f, Color.LTGRAY, width = column - 16f)
                text(macro.second, x, 1740f, 58f, Color.WHITE, width = column - 16f)
            }
            val logoWidth = 60f * logo.width / logo.height
            canvas.drawBitmap(logo, null, RectF(980f - logoWidth, 1354f, 980f, 1414f), Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG))
            val file = File.createTempFile("fit-meal-share-", ".jpg", directory(context))
            try {
                file.outputStream().use { if (!result.compress(Bitmap.CompressFormat.JPEG, 90, it)) throw IOException("Não foi possível criar a imagem.") }
            } catch (error: Exception) { file.delete(); throw error }
            return file.absolutePath
        } finally {
            photo.recycle(); logo.recycle(); result.recycle()
        }
    }
}
