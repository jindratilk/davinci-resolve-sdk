// Generated public-safe SDK action descriptors. Do not edit.
export const SDK_LOW_LEVEL_RUNTIME_BINDINGS = [
  {
    "actionId": "cutagent.action.audio.voice_list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "accent": {
          "minLength": 1,
          "type": "string"
        },
        "age": {
          "minLength": 1,
          "type": "string"
        },
        "gender": {
          "minLength": 1,
          "type": "string"
        },
        "includeCustomRates": {
          "type": "boolean"
        },
        "language": {
          "minLength": 1,
          "type": "string"
        },
        "limit": {
          "maximum": 100,
          "minimum": 1,
          "type": "integer"
        },
        "page": {
          "minimum": 0,
          "type": "integer"
        },
        "pageToken": {
          "minLength": 1,
          "type": "string"
        },
        "search": {
          "minLength": 1,
          "type": "string"
        },
        "sort": {
          "enum": [
            "trending",
            "usage_character_count_1y",
            "cloned_by_count",
            "created_date"
          ]
        },
        "source": {
          "enum": [
            "account",
            "library"
          ]
        },
        "useCase": {
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.cache_state",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "cacheType": {
          "type": "string"
        },
        "clip": {
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.current",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.fusion.by_name",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        },
        "name": {
          "type": "string"
        }
      },
      "required": [
        "clip",
        "name"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.fusion.tool_get",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "type": "string"
        },
        "compIndex": {
          "type": "integer"
        },
        "inputName": {
          "type": "string"
        },
        "recordFrame": {
          "type": "string"
        },
        "toolName": {
          "type": "string"
        },
        "track": {
          "type": "integer"
        }
      },
      "required": [
        "inputName",
        "toolName"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.fusion.tools",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "type": "string"
        },
        "index": {
          "type": "integer"
        },
        "recordFrame": {
          "type": "string"
        },
        "track": {
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.info",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "name": {
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "index": {
          "type": "integer"
        },
        "trackType": {
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.marker.get_custom",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        },
        "clipOrData": {
          "type": "string"
        },
        "maybeData": {
          "type": "string"
        }
      },
      "required": [
        "clipOrData"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.marker.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "name": {
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.source_audio_mapping",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.stereo_values",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.adr.info",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "limit": {
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.ai.read",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.api_notes",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.automation.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "contextBytes": {
          "type": "integer"
        },
        "includeContext": {
          "type": "boolean"
        },
        "limit": {
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.bus.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "contextBytes": {
          "type": "integer"
        },
        "includeContext": {
          "type": "boolean"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.channel_map.media",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        }
      },
      "required": [
        "clip"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.clip.info",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.clip.linked.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "maxLength": 1024,
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [
        "clipName"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.clip.source_range",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "maxLength": 1024,
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [
        "clipName"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.clip.track_info",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "maxLength": 1024,
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [
        "clipName"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.dynamics.read",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "track": {
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.effect.catalog",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.effect.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "bus": {
          "type": "string"
        },
        "clip": {
          "type": "string"
        },
        "track": {
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.effect.params",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "maxLength": 4096,
          "minLength": 1,
          "type": "string"
        },
        "effect": {
          "maxLength": 4096,
          "minLength": 1,
          "type": "string"
        },
        "track": {
          "minimum": 1,
          "type": "integer"
        }
      },
      "required": [
        "effect"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.effect.plugin_catalog",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "limit": {
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.effect.slot_scan",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "limit": {
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.elastic.info",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "limit": {
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.eq.read",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.external_process.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "limit": {
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.group.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "limit": {
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.index.clips",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "limit": {
          "type": "integer"
        },
        "query": {
          "type": "string"
        },
        "track": {
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.index.markers",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.index.tracks",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.info",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "index": {
          "type": "integer"
        }
      },
      "required": [
        "index"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.io.info",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "limit": {
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.items",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "index": {
          "type": "integer"
        }
      },
      "required": [
        "index"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.loudness.info",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "limit": {
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.mixer.meter_settings",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "limit": {
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.mixer.read",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "oneOf": [
        {
          "not": {
            "properties": {
              "bus": {
                "enum": [
                  "Main",
                  "Main 1",
                  "Bus 1"
                ],
                "type": "string"
              }
            },
            "required": [
              "bus"
            ]
          },
          "properties": {
            "track": {
              "minimum": 1,
              "type": "integer"
            }
          },
          "required": [
            "track"
          ]
        },
        {
          "not": {
            "properties": {
              "track": {
                "minimum": 1,
                "type": "integer"
              }
            },
            "required": [
              "track"
            ]
          },
          "properties": {
            "bus": {
              "enum": [
                "Main",
                "Main 1",
                "Bus 1"
              ],
              "type": "string"
            }
          },
          "required": [
            "bus"
          ]
        }
      ],
      "properties": {
        "bus": {
          "enum": [
            "Main",
            "Main 1",
            "Bus 1"
          ],
          "type": "string"
        },
        "track": {
          "minimum": 1,
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.monitor.info",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "limit": {
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.preset.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.record.info",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "limit": {
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.send.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "contextBytes": {
          "type": "integer"
        },
        "includeContext": {
          "type": "boolean"
        },
        "limit": {
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.sound_library.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "libraryScope": {
          "enum": [
            "project",
            "user"
          ]
        },
        "limit": {
          "type": "integer"
        },
        "query": {
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    },
    "publicPathPatterns": [
      [
        "library",
        "items",
        "*",
        "path"
      ]
    ]
  },
  {
    "actionId": "cutagent.action.fairlight.sound_library.search",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "libraryScope": {
          "enum": [
            "project",
            "user"
          ]
        },
        "limit": {
          "maximum": 500,
          "minimum": 1,
          "type": "integer"
        },
        "query": {
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [
        "query"
      ],
      "type": "object"
    },
    "publicPathPatterns": [
      [
        "matches",
        "items",
        "*",
        "path"
      ]
    ]
  },
  {
    "actionId": "cutagent.action.fairlight.track.height",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "index": {
          "type": "integer"
        },
        "size": {
          "type": "string"
        }
      },
      "required": [
        "index"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.tracks",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.vca.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.voice_isolation.get",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "track": {
          "type": "integer"
        }
      },
      "required": [
        "track"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fairlight.waveform.info",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fusion.preview",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "boldStyle": {
          "maxLength": 1024,
          "minLength": 1,
          "type": "string"
        },
        "text": {
          "maxLength": 1024,
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [
        "text"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.fusion.template.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    },
    "publicPathPatterns": [
      [
        "*",
        "path"
      ],
      [
        "templates",
        "*",
        "path"
      ]
    ]
  },
  {
    "actionId": "cutagent.action.media.audio_mapping",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        }
      },
      "required": [
        "clip"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.folders.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.folders.tree",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    },
    "publicRecursivePathRules": [
      {
        "pathKey": "path",
        "childrenKey": "subfolders"
      }
    ]
  },
  {
    "actionId": "cutagent.action.media.info",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "name": {
          "type": "string"
        }
      },
      "required": [
        "name"
      ],
      "type": "object"
    },
    "publicPathPatterns": [
      [
        "File Path"
      ],
      [
        "Proxy Media Path"
      ]
    ]
  },
  {
    "actionId": "cutagent.action.media.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "includeGenerated": {
          "type": "boolean"
        },
        "kind": {
          "type": "string"
        },
        "recursive": {
          "type": "boolean"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.mark.get",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        }
      },
      "required": [
        "clip"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.marker.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "name": {
          "type": "string"
        }
      },
      "required": [
        "name"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.matte.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        }
      },
      "required": [
        "clip"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.search",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "exact": {
          "type": "boolean"
        },
        "includeGenerated": {
          "type": "boolean"
        },
        "kind": {
          "type": "string"
        },
        "query": {
          "type": "string"
        }
      },
      "required": [
        "query"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.selected.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.third_party_metadata.get",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        },
        "key": {
          "type": "string"
        }
      },
      "required": [
        "clip"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.media.timeline_matte.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "folder": {
          "type": "string"
        }
      },
      "required": [
        "folder"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.page.current",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.project.folders.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    },
    "publicPathPatterns": [
      [
        "current_path"
      ],
      [
        "data",
        "folder",
        "path"
      ],
      [
        "folder",
        "path"
      ],
      [
        "folders",
        "*",
        "path"
      ],
      [
        "payload",
        "data",
        "folder",
        "path"
      ]
    ]
  },
  {
    "actionId": "cutagent.action.project.info",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.project.library.current",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.project.library.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.project.preset.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.project.settings",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "key": {
          "maxLength": 1024,
          "type": [
            "string",
            "null"
          ]
        }
      },
      "required": [],
      "type": "object"
    },
    "publicPathPatterns": [
      [
        "perfCacheClipsLocation"
      ]
    ]
  },
  {
    "actionId": "cutagent.action.render.codecs",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "format": {
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [
        "format"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.render.formats",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.render.job_status",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "jobId": {
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [
        "jobId"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.render.jobs",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.render.mode.get",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.render.presets",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.render.quick_export_presets",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.render.resolutions",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "codec": {
          "minLength": 1,
          "type": "string"
        },
        "format": {
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.render.settings",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.render.status",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "jobId": {
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.system.keyframe_mode.get",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.text.inspect",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "kind": {
          "enum": [
            "auto",
            "clip",
            "preset",
            "template"
          ]
        },
        "target": {
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [
        "target"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.text.list_presets",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {},
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.version.inspect",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "checkpointId": {
          "maxLength": 256,
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [
        "checkpointId"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.version.list",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "projectName": {
          "maxLength": 1024,
          "type": [
            "string",
            "null"
          ]
        },
        "sessionId": {
          "maxLength": 256,
          "type": [
            "string",
            "null"
          ]
        },
        "timelineName": {
          "maxLength": 1024,
          "type": [
            "string",
            "null"
          ]
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.version.status",
    "operationClass": "read",
    "idempotencyCategory": "safe_repeat",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "sessionId": {
          "maxLength": 256,
          "type": [
            "string",
            "null"
          ]
        }
      },
      "required": [],
      "type": "object"
    }
  }
];
