package fit.tracker.android

class WorkoutGIFAndroidView(context: android.content.Context) : android.view.View(context) {
    private var encoded: String? = null
    private var movie: android.graphics.Movie? = null
    private var playing = false
    private var started = 0L
    private var elapsed = 0L
    private var image: android.graphics.Bitmap? = null

    init { setLayerType(android.view.View.LAYER_TYPE_SOFTWARE, null) }

    fun update(value: String, animate: Boolean) {
        if (encoded != value) {
            encoded = value
            val bytes = android.util.Base64.decode(value, android.util.Base64.DEFAULT)
            movie = android.graphics.Movie.decodeByteArray(bytes, 0, bytes.size)
            image = if (movie == null) android.graphics.BitmapFactory.decodeByteArray(bytes, 0, bytes.size) else null
            elapsed = 0L
            started = android.os.SystemClock.uptimeMillis()
        }
        if (animate && !playing) started = android.os.SystemClock.uptimeMillis() - elapsed
        if (!animate && playing) elapsed = android.os.SystemClock.uptimeMillis() - started
        playing = animate
        invalidate()
    }

    fun pause() { playing = false }

    override fun onDraw(canvas: android.graphics.Canvas) {
        super.onDraw(canvas)
        canvas.drawColor(android.graphics.Color.WHITE)
        val animation = movie
        if (animation != null) {
            val duration = animation.duration().takeIf { it > 0 } ?: 1000
            val time = if (playing) android.os.SystemClock.uptimeMillis() - started else elapsed
            animation.setTime((time % duration).toInt())
            val scale = minOf(width.toFloat() / animation.width(), height.toFloat() / animation.height())
            canvas.save()
            canvas.translate((width - animation.width() * scale) / 2f, (height - animation.height() * scale) / 2f)
            canvas.scale(scale, scale)
            animation.draw(canvas, 0f, 0f)
            canvas.restore()
            if (playing && isAttachedToWindow && visibility == android.view.View.VISIBLE) postInvalidateOnAnimation()
        } else {
            image?.let { bitmap ->
                val scale = minOf(width.toFloat() / bitmap.width, height.toFloat() / bitmap.height)
                val left = (width - bitmap.width * scale) / 2f
                val top = (height - bitmap.height * scale) / 2f
                canvas.drawBitmap(bitmap, null, android.graphics.RectF(left, top, left + bitmap.width * scale, top + bitmap.height * scale), android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG))
            }
        }
    }

    override fun onDetachedFromWindow() { playing = false; super.onDetachedFromWindow() }
}

object NativeWorkoutPlatform {
    @androidx.compose.runtime.Composable
    fun GIF(encoded: String, animate: Boolean, modifier: androidx.compose.ui.Modifier) {
        androidx.compose.ui.viewinterop.AndroidView(
            modifier = modifier,
            factory = { viewContext -> WorkoutGIFAndroidView(viewContext) },
            onReset = null,
            onRelease = { view -> view.pause() },
            update = { view -> view.update(encoded, animate) },
        )
    }

    fun render(photo: String, logo: String, workout: String, caption: String,
               exercise: String, load: String, sets: String, reps: String): String? {
    try {
        val bitmap = android.graphics.Bitmap.createBitmap(1080, 1920, android.graphics.Bitmap.Config.ARGB_8888)
        val canvas = android.graphics.Canvas(bitmap)
        canvas.scale(3f, 3f)
        val paint = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG)
        fun decode(value: String): android.graphics.Bitmap? {
            val bytes = android.util.Base64.decode(value, android.util.Base64.DEFAULT)
            return android.graphics.BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
        }
        if (photo.isNotEmpty()) {
            val background = decode(photo) ?: return null
            val scale = maxOf(360f / background.width, 640f / background.height)
            val left = (360f - background.width * scale) / 2f
            val top = (640f - background.height * scale) / 2f
            canvas.drawBitmap(background, null, android.graphics.RectF(left, top, left + background.width * scale, top + background.height * scale), paint)
            background.recycle()
            paint.shader = android.graphics.LinearGradient(0f, 427f, 0f, 640f, 0, 0x4D000000, android.graphics.Shader.TileMode.CLAMP)
            canvas.drawRect(0f, 427f, 360f, 640f, paint)
        } else {
            canvas.drawColor(android.graphics.Color.rgb(6, 11, 19))
            paint.shader = android.graphics.RadialGradient(290f, 170f, 210f, android.graphics.Color.argb(77, 0, 122, 255), 0, android.graphics.Shader.TileMode.CLAMP)
            canvas.drawRect(0f, 0f, 360f, 640f, paint)
        }
        paint.shader = null
        paint.color = android.graphics.Color.argb(if (photo.isEmpty()) 240 else 173, 4, 9, 17)
        val panel = android.graphics.RectF(15f, 438.667f, 345f, 628f)
        canvas.drawRoundRect(panel, 15f, 15f, paint)
        paint.style = android.graphics.Paint.Style.STROKE
        paint.strokeWidth = 1f
        paint.color = android.graphics.Color.argb(204, 50, 173, 230)
        canvas.drawRoundRect(panel, 15f, 15f, paint)
        paint.style = android.graphics.Paint.Style.FILL
        fun text(value: String, x: Float, baseline: Float, size: Float, bold: Boolean, alpha: Int = 255, maxWidth: Float = 280f) {
            paint.color = android.graphics.Color.argb(alpha, 255, 255, 255)
            paint.typeface = android.graphics.Typeface.create("sans-serif", if (bold) android.graphics.Typeface.BOLD else android.graphics.Typeface.NORMAL)
            paint.textSize = size
            while (paint.measureText(value) > maxWidth && paint.textSize > size * 0.65f) paint.textSize -= 0.25f
            val output = android.text.TextUtils.ellipsize(value, android.text.TextPaint(paint), maxWidth, android.text.TextUtils.TruncateAt.END).toString()
            canvas.drawText(output, x, baseline, paint)
        }
        text(workout, 29f, 477f, 27f, true, maxWidth = 260f)
        text(caption, 29f, 492f, 10f, true, 204, 260f)
        val brand = decode(logo) ?: return null
        val logoScale = minOf(26f / brand.width, 26f / brand.height)
        val logoLeft = 305f + (26f - brand.width * logoScale) / 2f
        val logoTop = 453f + (26f - brand.height * logoScale) / 2f
        canvas.drawBitmap(brand, null, android.graphics.RectF(logoLeft, logoTop, logoLeft + brand.width * logoScale, logoTop + brand.height * logoScale), paint.apply { alpha = 255 })
        brand.recycle()
        paint.color = android.graphics.Color.argb(46, 255, 255, 255)
        canvas.drawRect(29f, 506f, 331f, 506.5f, paint)
        val exercisePaint = android.text.TextPaint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
            color = android.graphics.Color.WHITE
            textSize = 17f
            typeface = android.graphics.Typeface.create("sans-serif", android.graphics.Typeface.BOLD)
        }
        val exerciseText = android.text.StaticLayout.Builder.obtain(exercise, 0, exercise.length, exercisePaint, 302)
            .setMaxLines(2).setEllipsize(android.text.TextUtils.TruncateAt.END).setIncludePad(false).build()
        canvas.save()
        canvas.translate(29f, 517f)
        exerciseText.draw(canvas)
        canvas.restore()
        val values = arrayOf(load, sets, reps)
        val labels = arrayOf("CARGA", "SÉRIES", "REPS")
        for (index in values.indices) {
            val x = 29f + index * (302f / 3f)
            text(labels[index], x, 565f, 8f, true, 158, 90f)
            text(values[index], x, 595f, 24f, true, maxWidth = 90f)
            if (index == 0 && load != "—" && load != "Varia") {
                val loadWidth = paint.measureText(load)
                text("kg", x + loadWidth + 2f, 595f, 8f, false, 191, 20f)
            }
        }
        val app = skip.foundation.ProcessInfo.processInfo.androidContext
        val file = java.io.File.createTempFile("fittracker-workout-", ".png", NativePhotoPlatform.directory(app))
        java.io.FileOutputStream(file).use { output -> bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, output) }
        bitmap.recycle()
        return file.absolutePath
    } catch (error: Exception) {
        return null
    }
    }
}
