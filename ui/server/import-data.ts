import fs from 'fs';
import { db } from './db';
import { zones, places } from '@shared/schema';

if (!db) {
  throw new Error('Database connection not initialized. Set DATABASE_URL before running import-data.');
}

const database = db;

// Parse PostGIS MULTIPOLYGON format to extract coordinates
function parseMultiPolygon(wkt: string): any {
  if (!wkt || wkt === 'NULL') return null;
  
  // Remove SRID prefix if present
  const cleanWkt = wkt.replace(/^SRID=\d+;/, '');
  
  // Parse MULTIPOLYGON string
  if (cleanWkt.startsWith('MULTIPOLYGON')) {
    const coordsMatch = cleanWkt.match(/MULTIPOLYGON\(\(\((.*?)\)\)\)/);
    if (coordsMatch) {
      const coordsStr = coordsMatch[1];
      // Split by comma and parse coordinate pairs
      const coordPairs = coordsStr.split(',').map(pair => {
        const [lng, lat] = pair.trim().split(' ').map(Number);
        return [lng, lat];
      });
      
      // Return as GeoJSON-like structure
      return {
        type: 'MultiPolygon',
        coordinates: [[coordPairs]]
      };
    }
  }
  
  return null;
}

// Parse PostGIS POINTZM format to extract lat/lng
function parsePointZM(wkt: string): { latitude: number; longitude: number; elevation?: number } | null {
  if (!wkt || wkt === 'NULL') return null;
  
  // Remove SRID prefix if present
  const cleanWkt = wkt.replace(/^SRID=\d+;/, '');
  
  // Parse POINTZM string
  if (cleanWkt.startsWith('POINTZM')) {
    const coordsMatch = cleanWkt.match(/POINTZM\(([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\)/);
    if (coordsMatch) {
      const longitude = parseFloat(coordsMatch[1]);
      const latitude = parseFloat(coordsMatch[2]);
      const elevation = parseFloat(coordsMatch[3]);
      return { latitude, longitude, elevation };
    }
  }
  
  return null;
}

async function importZones() {
  console.log('Importing zones...');
  
  const zonesData = fs.readFileSync('/tmp/zones_data.sql', 'utf-8');
  const lines = zonesData.split('\n');
  
  const zoneRecords: any[] = [];
  
  for (const line of lines) {
    if (line.startsWith('(')) {
      // Parse zone record
      const match = line.match(/\((\d+),\s*'([^']*)'(?:,\s*'([^']*)')?(?:,\s*NULL)?(?:,\s*'([^']*)')?\)/);
      if (match) {
        const id = parseInt(match[1]);
        const name = match[2];
        const summary = match[3] && match[3] !== 'NULL' ? match[3] : null;
        const boundaryWkt = match[4] || null;
        
        const boundary = boundaryWkt ? parseMultiPolygon(boundaryWkt) : null;
        
        zoneRecords.push({
          id,
          name,
          summary,
          boundary
        });
      }
    }
  }
  
  // Insert zones into database
  for (const zone of zoneRecords) {
    try {
      await database.insert(zones).values(zone).onConflictDoNothing();
      console.log(`Inserted zone: ${zone.name} (${zone.id})`);
    } catch (error) {
      console.error(`Error inserting zone ${zone.id}:`, error);
    }
  }
  
  console.log(`Imported ${zoneRecords.length} zones`);
  return zoneRecords.length;
}

async function importPlaces() {
  console.log('Importing places...');
  
  const placesData = fs.readFileSync('/tmp/places_complete.sql', 'utf-8');
  
  // Extract place records using regex - handle multi-line records
  const placePattern = /\((\d+),\s*'([\s\S]*?)',\s*'([\s\S]*?)',\s*(\d+),\s*((?:'[\s\S]*?'|NULL)),\s*((?:'[\s\S]*?'|NULL)),\s*((?:'[\s\S]*?'|NULL)),\s*((?:'[\s\S]*?'|NULL)),\s*((?:'[\s\S]*?'|NULL)),\s*((?:'[\s\S]*?'|NULL)),\s*'[\s\S]*?',\s*'[\s\S]*?',\s*((?:'SRID=4326;POINTZM\([^)]*\)'|NULL)),\s*(?:'SRID=4326;POINTZM\([^)]*\)'|NULL)\)/g;
  
  const placeRecords: any[] = [];
  let match;
  
  while ((match = placePattern.exec(placesData)) !== null) {
    const id = parseInt(match[1]);
    const name = match[2];
    const type = match[3];
    const zoneId = parseInt(match[4]);
    const summary = match[5] !== 'NULL' ? match[5].replace(/^'|'$/g, '').replace(/''/g, "'") : null;
    const coordsWkt = match[11] !== 'NULL' ? match[11].replace(/^'|'$/g, '') : null;
    
    let latitude = null;
    let longitude = null;
    let elevation = null;
    
    if (coordsWkt) {
      const coords = parsePointZM(coordsWkt);
      if (coords) {
        latitude = coords.latitude.toString();
        longitude = coords.longitude.toString();
        elevation = coords.elevation?.toString() || null;
      }
    }
    
    placeRecords.push({
      id,
      name,
      type,
      summary,
      latitude,
      longitude,
      elevation,
      zoneId
    });
  }
  
  // Insert places into database
  for (const place of placeRecords) {
    try {
      await database.insert(places).values(place).onConflictDoNothing();
      console.log(`Inserted place: ${place.name} (${place.id})`);
    } catch (error) {
      console.error(`Error inserting place ${place.id}:`, error);
    }
  }
  
  console.log(`Imported ${placeRecords.length} places`);
  return placeRecords.length;
}

async function main() {
  console.log('Starting data import...');
  
  try {
    // Clear existing data
    console.log('Clearing existing data...');
    await database.delete(places);
    await database.delete(zones);
    
    // Import zones first (places reference zones)
    const zonesCount = await importZones();
    
    // Import places
    const placesCount = await importPlaces();
    
    console.log(`\nImport complete!`);
    console.log(`- Imported ${zonesCount} zones`);
    console.log(`- Imported ${placesCount} places`);
    
    // Verify import
    const zoneCount = await database.select().from(zones);
    const placeCount = await database.select().from(places);
    
    console.log(`\nVerification:`);
    console.log(`- Zones in database: ${zoneCount.length}`);
    console.log(`- Places in database: ${placeCount.length}`);
    
  } catch (error) {
    console.error('Import failed:', error);
    process.exit(1);
  }
  
  process.exit(0);
}

main();
