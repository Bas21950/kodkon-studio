param(
    [string]$OutputPath = (Join-Path $PSScriptRoot '..\frontend\public\kodkon-studio.ico')
)

$ErrorActionPreference = 'Stop'
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputPath)
$outputDirectory = Split-Path -Parent $resolvedOutput
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null

Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @'
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;

public static class KodKonStudioIconBuilder
{
    private static GraphicsPath Rounded(float x, float y, float width, float height, float radius)
    {
        float diameter = radius * 2f;
        GraphicsPath path = new GraphicsPath();
        path.AddArc(x, y, diameter, diameter, 180, 90);
        path.AddArc(x + width - diameter, y, diameter, diameter, 270, 90);
        path.AddArc(x + width - diameter, y + height - diameter, diameter, diameter, 0, 90);
        path.AddArc(x, y + height - diameter, diameter, diameter, 90, 90);
        path.CloseFigure();
        return path;
    }

    private static void DrawSparkle(Graphics graphics, float centerX, float centerY, float size, Color color)
    {
        PointF[] points = new PointF[] {
            new PointF(centerX, centerY - size),
            new PointF(centerX + size * 0.22f, centerY - size * 0.22f),
            new PointF(centerX + size, centerY),
            new PointF(centerX + size * 0.22f, centerY + size * 0.22f),
            new PointF(centerX, centerY + size),
            new PointF(centerX - size * 0.22f, centerY + size * 0.22f),
            new PointF(centerX - size, centerY),
            new PointF(centerX - size * 0.22f, centerY - size * 0.22f)
        };
        using (SolidBrush brush = new SolidBrush(color)) graphics.FillPolygon(brush, points);
    }

    public static Bitmap Render(int size)
    {
        Bitmap bitmap = new Bitmap(size, size, PixelFormat.Format32bppArgb);
        using (Graphics graphics = Graphics.FromImage(bitmap))
        {
            graphics.SmoothingMode = SmoothingMode.AntiAlias;
            graphics.InterpolationMode = InterpolationMode.HighQualityBicubic;
            graphics.PixelOffsetMode = PixelOffsetMode.HighQuality;
            graphics.CompositingQuality = CompositingQuality.HighQuality;
            graphics.Clear(Color.Transparent);
            graphics.ScaleTransform(size / 256f, size / 256f);

            using (GraphicsPath background = Rounded(8, 8, 240, 240, 55))
            using (LinearGradientBrush gradient = new LinearGradientBrush(
                new Rectangle(0, 0, 256, 256), Color.FromArgb(255, 121, 78), Color.FromArgb(236, 68, 89), 42f))
            {
                graphics.FillPath(gradient, background);
            }

            using (GraphicsPath cardShadow = Rounded(43, 41, 174, 184, 27))
            using (SolidBrush shadow = new SolidBrush(Color.FromArgb(48, 50, 25, 39)))
                graphics.FillPath(shadow, cardShadow);

            using (GraphicsPath card = Rounded(39, 34, 174, 184, 27))
            using (SolidBrush paper = new SolidBrush(Color.FromArgb(255, 253, 250)))
                graphics.FillPath(paper, card);

            using (SolidBrush avatar = new SolidBrush(Color.FromArgb(255, 104, 78)))
                graphics.FillEllipse(avatar, 58, 52, 23, 23);
            using (SolidBrush avatarDot = new SolidBrush(Color.White))
                graphics.FillEllipse(avatarDot, 65, 59, 9, 9);
            using (SolidBrush ink = new SolidBrush(Color.FromArgb(34, 45, 68)))
            using (GraphicsPath titleLine = Rounded(88, 54, 76, 7, 3))
                graphics.FillPath(ink, titleLine);
            using (SolidBrush mutedInk = new SolidBrush(Color.FromArgb(196, 202, 211)))
            using (GraphicsPath subtitleLine = Rounded(88, 66, 53, 5, 2))
                graphics.FillPath(mutedInk, subtitleLine);

            using (GraphicsPath preview = Rounded(59, 84, 135, 83, 16))
            using (SolidBrush previewFill = new SolidBrush(Color.FromArgb(255, 239, 228)))
                graphics.FillPath(previewFill, preview);
            using (SolidBrush sun = new SolidBrush(Color.FromArgb(255, 177, 86)))
                graphics.FillEllipse(sun, 78, 100, 21, 21);

            PointF[] farHill = new PointF[] {
                new PointF(62, 151), new PointF(96, 116), new PointF(120, 139),
                new PointF(143, 116), new PointF(190, 155), new PointF(190, 164), new PointF(62, 164)
            };
            using (SolidBrush hill = new SolidBrush(Color.FromArgb(255, 128, 103)))
                graphics.FillPolygon(hill, farHill);
            PointF[] nearHill = new PointF[] {
                new PointF(62, 157), new PointF(94, 132), new PointF(115, 151),
                new PointF(137, 129), new PointF(167, 157), new PointF(167, 164), new PointF(62, 164)
            };
            using (SolidBrush hill = new SolidBrush(Color.FromArgb(36, 49, 72)))
                graphics.FillPolygon(hill, nearHill);

            using (SolidBrush coral = new SolidBrush(Color.FromArgb(255, 104, 78)))
                graphics.FillEllipse(coral, 160, 128, 34, 34);
            PointF[] play = new PointF[] { new PointF(173, 136), new PointF(173, 154), new PointF(187, 145) };
            using (SolidBrush white = new SolidBrush(Color.White)) graphics.FillPolygon(white, play);

            using (SolidBrush ink = new SolidBrush(Color.FromArgb(36, 47, 70)))
            using (GraphicsPath captionLine = Rounded(60, 178, 116, 8, 4))
                graphics.FillPath(ink, captionLine);
            using (SolidBrush mutedInk = new SolidBrush(Color.FromArgb(180, 187, 198)))
            using (GraphicsPath detailLine = Rounded(60, 194, 77, 6, 3))
                graphics.FillPath(mutedInk, detailLine);

            PointF[] cursor = new PointF[] {
                new PointF(126, 139), new PointF(126, 197), new PointF(143, 181),
                new PointF(156, 211), new PointF(170, 205), new PointF(157, 175), new PointF(183, 175)
            };
            using (Pen outline = new Pen(Color.White, 10f))
            using (SolidBrush pointer = new SolidBrush(Color.FromArgb(29, 42, 65)))
            {
                outline.LineJoin = LineJoin.Round;
                graphics.DrawPolygon(outline, cursor);
                graphics.FillPolygon(pointer, cursor);
            }

            DrawSparkle(graphics, 204, 48, 11, Color.White);
            DrawSparkle(graphics, 222, 78, 5, Color.FromArgb(255, 226, 178));
        }
        return bitmap;
    }
}
'@ -ReferencedAssemblies System.Drawing

$sizes = [int[]](16, 24, 32, 48, 64, 128, 256)
$frames = foreach ($size in $sizes) {
    $bitmap = [KodKonStudioIconBuilder]::Render($size)
    $buffer = [System.IO.MemoryStream]::new()
    try { $bitmap.Save($buffer, [System.Drawing.Imaging.ImageFormat]::Png) }
    finally { $bitmap.Dispose() }
    [pscustomobject]@{ Size = $size; Png = $buffer.ToArray() }
    $buffer.Dispose()
}

$stream = [System.IO.MemoryStream]::new()
$writer = [System.IO.BinaryWriter]::new($stream)
try {
    $writer.Write([UInt16]0)
    $writer.Write([UInt16]1)
    $writer.Write([UInt16]$frames.Count)
    $offset = 6 + (16 * $frames.Count)
    foreach ($frame in $frames) {
        $dimension = if ($frame.Size -eq 256) { 0 } else { [byte]$frame.Size }
        $writer.Write([byte]$dimension)
        $writer.Write([byte]$dimension)
        $writer.Write([byte]0)
        $writer.Write([byte]0)
        $writer.Write([UInt16]1)
        $writer.Write([UInt16]32)
        $writer.Write([UInt32]$frame.Png.Length)
        $writer.Write([UInt32]$offset)
        $offset += $frame.Png.Length
    }
    foreach ($frame in $frames) { $writer.Write([byte[]]$frame.Png) }
    [System.IO.File]::WriteAllBytes($resolvedOutput, $stream.ToArray())
}
finally {
    $writer.Dispose()
    $stream.Dispose()
}

Write-Output "Created Windows icon: $resolvedOutput"
