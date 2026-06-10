-- Fallback missing market coordinates to their respective regency centroids
UPDATE dim_markets m
SET 
    latitude = r.latitude,
    longitude = r.longitude
FROM dim_regencies r
WHERE 
    m.regency_id = r.regency_id 
    AND m.latitude IS NULL;

-- Verify that there are no longer any NULL coordinates
SELECT COUNT(*) AS remaining_null_coordinates
FROM dim_markets
WHERE latitude IS NULL OR longitude IS NULL;
