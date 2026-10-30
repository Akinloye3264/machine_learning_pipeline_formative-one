const trafficDb = db.getSiblingDB("traffic_db");
const collectionName = "traffic_observations";

const validator = {
    $jsonSchema: {
        bsonType: "object",
        required: [
            "date_time",
            "traffic_volume",
            "weather"
        ],
        properties: {
            date_time: {
                bsonType: "date",
                description: "Must be a MongoDB date"
            },
            traffic_volume: {
                bsonType: "int",
                minimum: 0,
                description: "Must be a non-negative integer"
            },
            holiday: {
                bsonType: "string",
                description: "Optional holiday name"
            },
            weather: {
                bsonType: "array",
                minItems: 1,
                items: {
                    bsonType: "object",
                    required: [
                        "main",
                        "description",
                        "clouds_all"
                    ],
                    properties: {
                        main: {
                            bsonType: "string"
                        },
                        description: {
                            bsonType: "string"
                        },
                        temp_k: {
                            bsonType: "double"
                        },
                        rain_1h: {
                            bsonType: "double",
                            minimum: 0
                        },
                        snow_1h: {
                            bsonType: "double",
                            minimum: 0
                        },
                        clouds_all: {
                            bsonType: "int",
                            minimum: 0,
                            maximum: 100
                        }
                    }
                }
            }
        }
    }
};

const collectionExists = trafficDb
    .getCollectionNames()
    .includes(collectionName);

if (collectionExists) {
    const result = trafficDb.runCommand({
        collMod: collectionName,
        validator: validator,
        validationLevel: "strict",
        validationAction: "error"
    });

    if (!result.ok) {
        throw new Error(
            `Could not update validator: ${JSON.stringify(result)}`
        );
    }

    print("Updated validator on existing collection.");
} else {
    trafficDb.createCollection(collectionName, {
        validator: validator,
        validationLevel: "strict",
        validationAction: "error"
    });

    print("Created collection with validator.");
}

trafficDb
    .getCollection(collectionName)
    .createIndex(
        { date_time: 1 },
        {
            unique: true,
            name: "date_time_1"
        }
    );

print("Created or verified unique date_time index.");
print("MongoDB collection setup completed successfully.");