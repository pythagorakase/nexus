import type { Express } from "express";
import { createServer, type Server } from "http";
import { storage } from "./storage";
import { createProxyMiddleware } from "http-proxy-middleware";
import multer from "multer";
import fs from "fs/promises";
import path from "path";
import { parse as parseToml } from "toml";
import * as Toml from "@iarna/toml";
import sharp from "sharp";

// Register proxy BEFORE body parsing middleware
export function registerProxyRoutes(app: Express): void {
  const auditionPort = process.env.API_PORT || "8000";
  const auditionTarget = process.env.AUDITION_API_URL || `http://localhost:${auditionPort}`;
  const corePort = process.env.CORE_API_PORT || "8001";
  const coreTarget = process.env.CORE_API_URL || `http://localhost:${corePort}`;
  const narrativePort = process.env.NARRATIVE_API_PORT || "8002";
  const narrativeTarget = process.env.NARRATIVE_API_URL || `http://localhost:${narrativePort}`;

  // Proxy for Audition API (FastAPI backend on port 8000)
  // Express strips /api/audition before passing to middleware, so we need to add it back
  // IMPORTANT: Must be registered BEFORE express.json() to access raw body stream
  const auditionProxy = createProxyMiddleware({
    target: auditionTarget,
    changeOrigin: true,
    pathRewrite: (path) => `/api/audition${path}`,
  });

  app.use("/api/audition", auditionProxy);

  // Proxy for Core API (FastAPI backend on port 8001)
  // Handles model management and system operations
  const coreModelsProxy = createProxyMiddleware({
    target: coreTarget,
    changeOrigin: true,
    pathRewrite: (path) => `/api/models${path}`,
  });

  const coreHealthProxy = createProxyMiddleware({
    target: coreTarget,
    changeOrigin: true,
    pathRewrite: (path) => `/api/health${path === "/" ? "" : path}`,
  });

  app.use("/api/models", coreModelsProxy);
  app.use("/api/health", coreHealthProxy);

  // Proxy for Narrative API (FastAPI backend on port 8002)
  // Handles generation + incubator management without intercepting local narrative read routes
  const narrativeProxyOptions = {
    target: narrativeTarget,
    changeOrigin: true,
  };

  app.use("/api/narrative/continue", createProxyMiddleware(narrativeProxyOptions));
  app.use("/api/narrative/status", createProxyMiddleware(narrativeProxyOptions));
  app.use("/api/narrative/incubator", createProxyMiddleware(narrativeProxyOptions));
  app.use("/api/narrative/approve", createProxyMiddleware(narrativeProxyOptions));
  app.use("/ws/narrative", createProxyMiddleware({ ...narrativeProxyOptions, ws: true }));
}

export async function registerRoutes(app: Express): Promise<Server> {

  app.get("/status", (_req, res) => {
    res.json({ status: "ok" });
  });

  // Narrative routes
  
  // GET /api/narrative/seasons - Get all seasons
  app.get("/api/narrative/seasons", async (req, res) => {
    try {
      const seasons = await storage.getAllSeasons();
      res.json(seasons);
    } catch (error) {
      console.error("Error fetching seasons:", error);
      res.status(500).json({ error: "Failed to fetch seasons" });
    }
  });

  // GET /api/narrative/episodes/:seasonId - Get episodes by season
  app.get("/api/narrative/episodes/:seasonId", async (req, res) => {
    try {
      const seasonId = parseInt(req.params.seasonId);
      if (isNaN(seasonId)) {
        return res.status(400).json({ error: "Invalid season ID" });
      }
      
      const episodes = await storage.getEpisodesBySeason(seasonId);
      res.json(episodes);
    } catch (error) {
      console.error("Error fetching episodes:", error);
      res.status(500).json({ error: "Failed to fetch episodes" });
    }
  });

  // GET /api/narrative/latest-chunk - Get the newest chunk
  app.get("/api/narrative/latest-chunk", async (req, res) => {
    try {
      const chunk = await storage.getLatestChunk();
      if (!chunk) {
        return res.status(404).json({ error: "No chunks found" });
      }
      res.json(chunk);
    } catch (error) {
      console.error("Error fetching latest chunk:", error);
      res.status(500).json({ error: "Failed to fetch latest chunk" });
    }
  });

  // GET /api/narrative/chunks/:chunkId/adjacent - Get previous and next chunks
  app.get("/api/narrative/chunks/:chunkId/adjacent", async (req, res) => {
    try {
      const chunkId = parseInt(req.params.chunkId);
      if (isNaN(chunkId)) {
        return res.status(400).json({ error: "Invalid chunk ID" });
      }

      const result = await storage.getAdjacentChunks(chunkId);
      res.json(result);
    } catch (error) {
      console.error("Error fetching adjacent chunks:", error);
      res.status(500).json({ error: "Failed to fetch adjacent chunks" });
    }
  });

  // GET /api/narrative/chunks/:seasonId/:episodeId - Get chunks by season and episode with pagination
  app.get("/api/narrative/chunks/:seasonId/:episodeId", async (req, res) => {
    try {
      const seasonId = parseInt(req.params.seasonId);
      const episodeId = parseInt(req.params.episodeId);
      if (isNaN(seasonId) || isNaN(episodeId)) {
        return res.status(400).json({ error: "Invalid season or episode ID" });
      }

      const offset = parseInt(req.query.offset as string) || 0;
      const limit = parseInt(req.query.limit as string) || 50;

      const result = await storage.getChunksBySeasonAndEpisode(seasonId, episodeId, offset, limit);
      res.json(result);
    } catch (error) {
      console.error("Error fetching chunks:", error);
      res.status(500).json({ error: "Failed to fetch chunks" });
    }
  });

  // Character routes
  
  // GET /api/characters - Get all characters with optional ID range filter
  app.get("/api/characters", async (req, res) => {
    try {
      const startId = req.query.startId ? parseInt(req.query.startId as string) : undefined;
      const endId = req.query.endId ? parseInt(req.query.endId as string) : undefined;
      
      const characters = await storage.getCharacters(startId, endId);
      res.json(characters);
    } catch (error) {
      console.error("Error fetching characters:", error);
      res.status(500).json({ error: "Failed to fetch characters" });
    }
  });

  // GET /api/characters/:id/relationships - Get character relationships
  app.get("/api/characters/:id/relationships", async (req, res) => {
    try {
      const characterId = parseInt(req.params.id);
      if (isNaN(characterId)) {
        return res.status(400).json({ error: "Invalid character ID" });
      }
      
      const relationships = await storage.getCharacterRelationships(characterId);
      res.json(relationships);
    } catch (error) {
      console.error("Error fetching character relationships:", error);
      res.status(500).json({ error: "Failed to fetch character relationships" });
    }
  });

  // GET /api/characters/:id/psychology - Get character psychology
  app.get("/api/characters/:id/psychology", async (req, res) => {
    try {
      const characterId = parseInt(req.params.id);
      if (isNaN(characterId)) {
        return res.status(400).json({ error: "Invalid character ID" });
      }
      
      const psychology = await storage.getCharacterPsychology(characterId);
      if (!psychology) {
        return res.status(404).json({ error: "Character psychology not found" });
      }
      res.json(psychology);
    } catch (error) {
      console.error("Error fetching character psychology:", error);
      res.status(500).json({ error: "Failed to fetch character psychology" });
    }
  });

  // Place and Zone routes
  
  // GET /api/places - Get all places
  app.get("/api/places", async (req, res) => {
    try {
      const places = await storage.getAllPlaces();
      res.json(places);
    } catch (error) {
      console.error("Error fetching places:", error);
      res.status(500).json({ error: "Failed to fetch places" });
    }
  });

  // GET /api/zones - Get all zones
  app.get("/api/zones", async (req, res) => {
    try {
      const zones = await storage.getAllZones();
      res.json(zones);
    } catch (error) {
      console.error("Error fetching zones:", error);
      res.status(500).json({ error: "Failed to fetch zones" });
    }
  });

  // Additional faction route (for completeness)
  app.get("/api/factions", async (req, res) => {
    try {
      const factions = await storage.getAllFactions();
      res.json(factions);
    } catch (error) {
      console.error("Error fetching factions:", error);
      res.status(500).json({ error: "Failed to fetch factions" });
    }
  });

  // Settings routes
  const rootDir = path.join(process.cwd(), "..");
  const tomlSettingsPath = path.join(rootDir, "nexus.toml");
  const legacySettingsPath = path.join(rootDir, "settings.json");

  const buildSettingsPayload = (rawSettings: any) => ({
    ...rawSettings,
    "Agent Settings": {
      global: rawSettings?.global ?? {},
      LORE: rawSettings?.lore ?? rawSettings?.LORE ?? {},
      MEMNON: rawSettings?.memnon ?? rawSettings?.MEMNON ?? {},
    },
    "API Settings": {
      apex: rawSettings?.apex ?? rawSettings?.API?.apex ?? {},
    },
  });

  const readSettings = async () => {
    try {
      const tomlContent = await fs.readFile(tomlSettingsPath, "utf-8");
      return parseToml(tomlContent);
    } catch (error: any) {
      if (error?.code === "ENOENT") {
        console.warn("[settings] nexus.toml not found, falling back to legacy settings.json");
        const legacyContent = await fs.readFile(legacySettingsPath, "utf-8");
        return JSON.parse(legacyContent);
      }
      throw error;
    }
  };

  const escapeForRegex = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  const serializeTomlValue = (value: unknown) => {
    // Constrain supported types so we don't inject unsafe TOML fragments.
    const isPrimitive = (val: unknown) => ["string", "number", "boolean"].includes(typeof val);
    const isSupportedArray =
      Array.isArray(value) && value.every((item) => isPrimitive(item));

    if (!isPrimitive(value) && !isSupportedArray) {
      throw new Error(
        `Unsupported TOML value type: ${typeof value} (${JSON.stringify(value)})`,
      );
    }

    try {
      const serialized = Toml.stringify({ value });
      const match = serialized.match(/value\s*=\s*(.*)/);
      if (!match || !match[1]) {
        throw new Error(`Unable to extract serialized TOML literal for value: ${JSON.stringify(value)}`);
      }
      return match[1].trim();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unknown TOML serialization error";
      throw new Error(`Failed to serialize TOML value (${JSON.stringify(value)}): ${message}`);
    }
  };

  const replaceTomlValue = (content: string, section: string, key: string, value: unknown) => {
    const rawValue = serializeTomlValue(value);
    const sectionPattern = new RegExp(
      `\\[${escapeForRegex(section)}\\]\\s*\\n([\\s\\S]*?)(?=\\n\\[|$)`,
      "m",
    );
    const sectionMatch = content.match(sectionPattern);
    if (!sectionMatch) {
      throw new Error(`Section [${section}] not found in nexus.toml`);
    }

    const sectionBody = sectionMatch[1];
    // Capture groups:
    // 1: leading "key =" including whitespace
    // 2: current value
    // 3: trailing whitespace/comment (if present)
    const keyPattern = new RegExp(`(^\\s*${escapeForRegex(key)}\\s*=\\s*)([^#\\n]*?)(\\s*(#.*)?)$`, "m");

    let updatedBody: string;
    if (keyPattern.test(sectionBody)) {
      updatedBody = sectionBody.replace(keyPattern, (_match, prefix: string, _value: string, suffix: string) => {
        const trailing = suffix ?? "";
        return `${prefix}${rawValue}${trailing}`;
      });
    } else {
      const trimmed = sectionBody.trimEnd();
      const newline = trimmed.endsWith("\n") ? "" : "\n";
      updatedBody = `${trimmed}${newline}${key} = ${rawValue}\n`;
    }

    return content.replace(sectionPattern, `[${section}]\n${updatedBody}`);
  };

  app.head("/api/settings", async (_req, res) => {
    try {
      await readSettings();
      res.status(200).end();
    } catch (error) {
      console.error("Error fetching settings (HEAD):", error);
      res.status(500).end();
    }
  });

  app.get("/api/settings", async (_req, res) => {
    try {
      const settings = await readSettings();
      res.json(buildSettingsPayload(settings));
    } catch (error) {
      console.error("Error fetching settings:", error);
      res.status(500).json({ error: "Failed to fetch settings" });
    }
  });

  app.patch("/api/settings", async (req, res) => {
    try {
      let tomlContent = await fs.readFile(tomlSettingsPath, "utf-8");
      const updates = req.body;
      let appliedUpdates = 0;

      const narrativeUpdates = updates?.["Agent Settings"]?.global?.narrative ?? updates?.global?.narrative;
      if (narrativeUpdates && typeof narrativeUpdates === "object" && "test_mode" in narrativeUpdates) {
        const testMode = Boolean(narrativeUpdates.test_mode);
        tomlContent = replaceTomlValue(tomlContent, "global.narrative", "test_mode", testMode);
        appliedUpdates += 1;
      }

      const apexContextWindow =
        updates?.["Agent Settings"]?.LORE?.token_budget?.apex_context_window ??
        updates?.lore?.token_budget?.apex_context_window;
      if (typeof apexContextWindow === "number") {
        tomlContent = replaceTomlValue(
          tomlContent,
          "lore.token_budget",
          "apex_context_window",
          apexContextWindow,
        );
        appliedUpdates += 1;
      }

      if (!appliedUpdates) {
        return res.status(400).json({ error: "No supported settings provided" });
      }

      await fs.writeFile(tomlSettingsPath, tomlContent, "utf-8");
      const updatedSettings = await readSettings();

      res.json({ success: true, settings: buildSettingsPayload(updatedSettings) });
    } catch (error) {
      console.error("Error updating settings:", error);
      res.status(500).json({ error: "Failed to update settings" });
    }
  });

  // Multer configuration for file uploads
  const upload = multer({
    dest: "/tmp/",
    limits: {
      fileSize: 15 * 1024 * 1024, // 15MB max file size
    },
    fileFilter: (req, file, cb) => {
      // Accept only PNG, JPEG, and JPG
      const allowedMimeTypes = ['image/png', 'image/jpeg', 'image/jpg'];
      const allowedExtensions = ['.png', '.jpg', '.jpeg'];

      const ext = path.extname(file.originalname).toLowerCase();
      const mimeType = file.mimetype.toLowerCase();

      if (allowedMimeTypes.includes(mimeType) && allowedExtensions.includes(ext)) {
        cb(null, true);
      } else {
        cb(new Error(`Invalid file type. Only PNG and JPEG images are allowed. Got: ${file.mimetype}`));
      }
    },
  });

  // Character image routes
  app.get("/api/characters/:id/images", async (req, res) => {
    try {
      const characterId = parseInt(req.params.id);
      if (isNaN(characterId)) {
        return res.status(400).json({ error: "Invalid character ID" });
      }

      const images = await storage.getCharacterImages(characterId);
      res.json(images);
    } catch (error) {
      console.error("Error fetching character images:", error);
      res.status(500).json({ error: "Failed to fetch character images" });
    }
  });

  app.post("/api/characters/:id/images", upload.array("images", 10), async (req, res) => {
    try {
      const characterId = parseInt(req.params.id);
      if (isNaN(characterId)) {
        return res.status(400).json({ error: "Invalid character ID" });
      }

      if (!req.files || !Array.isArray(req.files) || req.files.length === 0) {
        return res.status(400).json({ error: "No files uploaded" });
      }

      const characterDir = path.join(import.meta.dirname, "..", "client", "public", "character_portraits", String(characterId));
      await fs.mkdir(characterDir, { recursive: true });

      // Get current max display order
      const existingImages = await storage.getCharacterImages(characterId);
      let maxOrder = existingImages.reduce((max, img) => Math.max(max, img.displayOrder), -1);

      const uploadedImages = [];
      for (const file of req.files) {
        // Sanitize filename: only allow alphanumeric, dash, underscore, and extension
        const ext = path.extname(file.originalname).toLowerCase();
        const sanitized = file.originalname
          .replace(ext, '')
          .replace(/[^a-zA-Z0-9_-]/g, '_')
          .substring(0, 50); // Limit base name length
        const filename = `${Date.now()}_${sanitized}${ext}`;
        const destPath = path.join(characterDir, filename);
        await fs.copyFile(file.path, destPath);
        await fs.unlink(file.path);

        const relativePath = `/character_portraits/${characterId}/${filename}`;
        const isMain = existingImages.length === 0 && uploadedImages.length === 0 ? 1 : 0;
        maxOrder++;

        const image = await storage.addCharacterImage(characterId, relativePath, isMain, maxOrder);
        uploadedImages.push(image);
      }

      res.json({ success: true, images: uploadedImages });
    } catch (error: any) {
      console.error("Error uploading character images:", error);
      // Handle multer-specific errors
      if (error.code === 'LIMIT_FILE_SIZE') {
        return res.status(413).json({ error: "File too large. Maximum size is 15MB." });
      }
      if (error.message && error.message.includes('Invalid file type')) {
        return res.status(400).json({ error: error.message });
      }
      res.status(500).json({ error: "Failed to upload images" });
    }
  });

  app.put("/api/characters/:id/images/:imageId/main", async (req, res) => {
    try {
      const characterId = parseInt(req.params.id);
      const imageId = parseInt(req.params.imageId);
      if (isNaN(characterId) || isNaN(imageId)) {
        return res.status(400).json({ error: "Invalid IDs" });
      }

      await storage.setMainCharacterImage(characterId, imageId);
      res.json({ success: true });
    } catch (error) {
      console.error("Error setting main character image:", error);
      res.status(500).json({ error: "Failed to set main image" });
    }
  });

  app.delete("/api/characters/:id/images/:imageId", async (req, res) => {
    try {
      const characterId = parseInt(req.params.id);
      const imageId = parseInt(req.params.imageId);
      if (isNaN(characterId) || isNaN(imageId)) {
        return res.status(400).json({ error: "Invalid IDs" });
      }

      // Get image info to delete file
      const images = await storage.getCharacterImages(characterId);
      const image = images.find(img => img.id === imageId);

      if (image) {
        const filePath = path.join(import.meta.dirname, "..", "client", "public", image.filePath);
        try {
          await fs.unlink(filePath);
        } catch (err) {
          console.warn("Could not delete image file:", filePath, err);
        }
      }

      await storage.deleteCharacterImage(imageId);
      res.json({ success: true });
    } catch (error) {
      console.error("Error deleting character image:", error);
      res.status(500).json({ error: "Failed to delete image" });
    }
  });

  // Place image routes
  app.get("/api/places/:id/images", async (req, res) => {
    try {
      const placeId = parseInt(req.params.id);
      if (isNaN(placeId)) {
        return res.status(400).json({ error: "Invalid place ID" });
      }

      const images = await storage.getPlaceImages(placeId);
      res.json(images);
    } catch (error) {
      console.error("Error fetching place images:", error);
      res.status(500).json({ error: "Failed to fetch place images" });
    }
  });

  app.post("/api/places/:id/images", upload.array("images", 10), async (req, res) => {
    try {
      const placeId = parseInt(req.params.id);
      if (isNaN(placeId)) {
        return res.status(400).json({ error: "Invalid place ID" });
      }

      if (!req.files || !Array.isArray(req.files) || req.files.length === 0) {
        return res.status(400).json({ error: "No files uploaded" });
      }

      const placeDir = path.join(import.meta.dirname, "..", "client", "public", "place_images", String(placeId));
      await fs.mkdir(placeDir, { recursive: true });

      // Get current max display order
      const existingImages = await storage.getPlaceImages(placeId);
      let maxOrder = existingImages.reduce((max, img) => Math.max(max, img.displayOrder), -1);

      const uploadedImages = [];
      for (const file of req.files) {
        // Sanitize filename: only allow alphanumeric, dash, underscore, and extension
        const ext = path.extname(file.originalname).toLowerCase();
        const sanitized = file.originalname
          .replace(ext, '')
          .replace(/[^a-zA-Z0-9_-]/g, '_')
          .substring(0, 50); // Limit base name length
        const filename = `${Date.now()}_${sanitized}${ext}`;
        const destPath = path.join(placeDir, filename);
        await fs.copyFile(file.path, destPath);
        await fs.unlink(file.path);

        const relativePath = `/place_images/${placeId}/${filename}`;
        const isMain = existingImages.length === 0 && uploadedImages.length === 0 ? 1 : 0;
        maxOrder++;

        const image = await storage.addPlaceImage(placeId, relativePath, isMain, maxOrder);
        uploadedImages.push(image);
      }

      res.json({ success: true, images: uploadedImages });
    } catch (error: any) {
      console.error("Error uploading place images:", error);
      // Handle multer-specific errors
      if (error.code === 'LIMIT_FILE_SIZE') {
        return res.status(413).json({ error: "File too large. Maximum size is 15MB." });
      }
      if (error.message && error.message.includes('Invalid file type')) {
        return res.status(400).json({ error: error.message });
      }
      res.status(500).json({ error: "Failed to upload images" });
    }
  });

  app.put("/api/places/:id/images/:imageId/main", async (req, res) => {
    try {
      const placeId = parseInt(req.params.id);
      const imageId = parseInt(req.params.imageId);
      if (isNaN(placeId) || isNaN(imageId)) {
        return res.status(400).json({ error: "Invalid IDs" });
      }

      await storage.setMainPlaceImage(placeId, imageId);
      res.json({ success: true });
    } catch (error) {
      console.error("Error setting main place image:", error);
      res.status(500).json({ error: "Failed to set main image" });
    }
  });

  app.delete("/api/places/:id/images/:imageId", async (req, res) => {
    try {
      const placeId = parseInt(req.params.id);
      const imageId = parseInt(req.params.imageId);
      if (isNaN(placeId) || isNaN(imageId)) {
        return res.status(400).json({ error: "Invalid IDs" });
      }

      // Get image info to delete file
      const images = await storage.getPlaceImages(placeId);
      const image = images.find(img => img.id === imageId);

      if (image) {
        const filePath = path.join(import.meta.dirname, "..", "client", "public", image.filePath);
        try {
          await fs.unlink(filePath);
        } catch (err) {
          console.warn("Could not delete image file:", filePath, err);
        }
      }

      await storage.deletePlaceImage(imageId);
      res.json({ success: true });
    } catch (error) {
      console.error("Error deleting place image:", error);
      res.status(500).json({ error: "Failed to delete image" });
    }
  });

  // PWA Icon upload route
  app.post("/api/settings/pwa-icon", upload.single("icon"), async (req, res) => {
    try {
      if (!req.file) {
        return res.status(400).json({ error: "No file uploaded" });
      }

      const tempPath = req.file.path;
      const iconsDir = path.join(import.meta.dirname, "..", "client", "public", "icons");

      // Generate all required icon sizes using sharp (safe, no shell execution)
      const sizes = [
        { size: 512, name: "icon-512.png" },
        { size: 192, name: "icon-192.png" },
        { size: 180, name: "apple-touch-icon.png" },
        { size: 32, name: "favicon-32.png" },
      ];

      for (const { size, name } of sizes) {
        const outputPath = path.join(iconsDir, name);
        await sharp(tempPath)
          .resize(size, size, { fit: "contain", background: { r: 0, g: 0, b: 0, alpha: 0 } })
          .png()
          .toFile(outputPath);
      }

      // Generate favicon.ico using sharp
      const faviconPath = path.join(import.meta.dirname, "..", "client", "public", "favicon.ico");

      // Sharp doesn't natively support ICO, so create a 32x32 PNG as favicon
      // Modern browsers support PNG favicons via <link rel="icon">
      await sharp(tempPath)
        .resize(32, 32, { fit: "contain", background: { r: 0, g: 0, b: 0, alpha: 0 } })
        .png()
        .toFile(faviconPath.replace('.ico', '.png'));

      // Copy source file for future reference
      const sourcePath = path.join(iconsDir, "icon-source.png");
      await fs.copyFile(tempPath, sourcePath);

      // Clean up temp file
      await fs.unlink(tempPath);

      // Update manifest.json with cache-busting timestamp
      const manifestPath = path.join(import.meta.dirname, "..", "client", "public", "manifest.json");
      const manifestData = await fs.readFile(manifestPath, "utf-8");
      const manifest = JSON.parse(manifestData);
      const timestamp = Date.now();

      // Add timestamp query parameter to all icon URLs
      manifest.icons = manifest.icons.map((icon: any) => ({
        ...icon,
        src: icon.src.split('?')[0] + `?v=${timestamp}` // Remove old timestamp if exists, add new one
      }));

      await fs.writeFile(manifestPath, JSON.stringify(manifest, null, 2), "utf-8");

      res.json({ success: true, message: "PWA icon updated successfully" });
    } catch (error) {
      console.error("Error uploading PWA icon:", error);
      res.status(500).json({ error: "Failed to upload icon" });
    }
  });

  const httpServer = createServer(app);

  return httpServer;
}
