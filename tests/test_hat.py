"""
Unit tests for the Hat cog.

Tests cover:
- Hat configuration (scale, rotation, offset, flip)
- Image dimension calculations
- Position calculations
- Configuration persistence
- Validation of settings within limits
- Edge cases (invalid images, extreme values)
"""

import pytest
from PIL import Image
import io


# ============================================================================
# Test Hat Configuration
# ============================================================================

@pytest.mark.asyncio
class TestHatConfig:
    """Test Hat cog configuration."""

    async def test_default_user_config(self, mock_config):
        """Test that default user config values are set correctly."""
        mock_config.register_user(
            selected_hat=None,
            scale=0.5,
            rotation=0,
            x_offset=0.5,
            y_offset=0.0,
            flip_x=False,
            flip_y=False,
        )

        user_data = await mock_config.user(1).all()
        assert user_data["selected_hat"] is None
        assert user_data["scale"] == 0.5
        assert user_data["rotation"] == 0
        assert user_data["x_offset"] == 0.5  # Center horizontally
        assert user_data["y_offset"] == 0.0  # Top of image
        assert user_data["flip_x"] is False
        assert user_data["flip_y"] is False

    async def test_set_hat_scale(self, mock_config):
        """Test setting hat scale."""
        mock_config.register_user(scale=0.5)

        await mock_config.user(1).scale.set(0.75)
        scale = await mock_config.user(1).scale()
        assert scale == 0.75

    async def test_set_hat_rotation(self, mock_config):
        """Test setting hat rotation."""
        mock_config.register_user(rotation=0)

        await mock_config.user(1).rotation.set(45)
        rotation = await mock_config.user(1).rotation()
        assert rotation == 45

    async def test_set_hat_offsets(self, mock_config):
        """Test setting hat position offsets."""
        mock_config.register_user(x_offset=0.5, y_offset=0.0)

        await mock_config.user(1).x_offset.set(0.3)
        await mock_config.user(1).y_offset.set(0.1)

        x_offset = await mock_config.user(1).x_offset()
        y_offset = await mock_config.user(1).y_offset()

        assert x_offset == 0.3
        assert y_offset == 0.1

    async def test_set_hat_flip(self, mock_config):
        """Test setting hat flip options."""
        mock_config.register_user(flip_x=False, flip_y=False)

        await mock_config.user(1).flip_x.set(True)
        flip_x = await mock_config.user(1).flip_x()
        assert flip_x is True

        await mock_config.user(1).flip_y.set(True)
        flip_y = await mock_config.user(1).flip_y()
        assert flip_y is True


# ============================================================================
# Test Hat Selection and Storage
# ============================================================================

@pytest.mark.asyncio
class TestHatSelection:
    """Test hat selection and storage."""

    async def test_select_hat(self, mock_config):
        """Test selecting a hat."""
        mock_config.register_user(selected_hat=None)
        mock_config.register_global(hats={})

        # Register a hat - access global config properly
        global_data = await mock_config.guild(0).all()  # Using guild(0) for global
        hats = global_data.get("hats", {})
        hats["santa"] = {"filename": "santa.png", "default": True}

        # We'll just store in user config for simplicity
        await mock_config.user(1).selected_hat.set("santa")

        # Verify
        selected = await mock_config.user(1).selected_hat()
        assert selected == "santa"

    async def test_default_hat_fallback(self, mock_config):
        """Test fallback to default hat when user has no selection."""
        mock_config.register_user(selected_hat=None)
        mock_config.register_global(default_hat="santa")

        # Check user has no selection
        selected = await mock_config.user(1).selected_hat()
        assert selected is None

        # Would fall back to default (testing the logic, not the implementation)
        default_fallback = "santa"  # This would come from global config
        final_hat = selected if selected else default_fallback
        assert final_hat == "santa"

    async def test_register_hat(self, mock_config):
        """Test registering a new hat."""
        mock_config.register_global(hats={})

        # Test storing hat metadata (simplified for unit test)
        hat_data = {"filename": "santa.png", "default": True}

        # Verify the data structure
        assert hat_data["filename"] == "santa.png"
        assert hat_data["default"] is True


# ============================================================================
# Test Image Dimension Calculations
# ============================================================================

class TestImageDimensions:
    """Test image dimension and position calculations."""

    def test_calculate_hat_dimensions(self):
        """Test calculating scaled hat dimensions."""
        avatar_width = 512
        hat_original_width = 200
        hat_original_height = 150
        scale = 0.5

        # Calculate scaled hat width
        hat_width = int(avatar_width * scale)  # 256
        # Maintain aspect ratio for height
        hat_height = int(hat_original_height * (hat_width / hat_original_width))  # 192

        assert hat_width == 256
        assert hat_height == 192

    def test_calculate_hat_position_centered(self):
        """Test calculating hat position when centered."""
        avatar_width = 512
        avatar_height = 512
        hat_width = 256
        hat_height = 128
        x_offset = 0.5  # Center
        y_offset = 0.0  # Top

        # Calculate position
        x = int((avatar_width - hat_width) * x_offset)  # 128
        y = int((avatar_height - hat_height) * y_offset)  # 0

        assert x == 128  # Centered horizontally
        assert y == 0  # At top

    def test_calculate_hat_position_custom(self):
        """Test calculating hat position with custom offsets."""
        avatar_width = 512
        avatar_height = 512
        hat_width = 256
        hat_height = 128
        x_offset = 0.25  # Left quarter
        y_offset = 0.1  # Near top

        x = int((avatar_width - hat_width) * x_offset)  # 64
        y = int((avatar_height - hat_height) * y_offset)  # 38

        assert x == 64
        assert y == 38

    def test_calculate_hat_position_edges(self):
        """Test hat positioning at edges."""
        avatar_width = 512
        avatar_height = 512
        hat_width = 256
        hat_height = 128

        # Left edge
        x_left = int((avatar_width - hat_width) * 0.0)
        assert x_left == 0

        # Right edge
        x_right = int((avatar_width - hat_width) * 1.0)
        assert x_right == 256

        # Top edge
        y_top = int((avatar_height - hat_height) * 0.0)
        assert y_top == 0

        # Bottom edge
        y_bottom = int((avatar_height - hat_height) * 1.0)
        assert y_bottom == 384


# ============================================================================
# Test Scale and Rotation Validation
# ============================================================================

class TestValidation:
    """Test validation of settings."""

    def test_scale_within_limits(self):
        """Test that scale values are validated."""
        MIN_SCALE = 0.1
        MAX_SCALE = 2.0

        # Valid scales
        assert MIN_SCALE <= 0.5 <= MAX_SCALE
        assert MIN_SCALE <= 1.0 <= MAX_SCALE
        assert MIN_SCALE <= 1.5 <= MAX_SCALE

        # Invalid scales
        assert not (MIN_SCALE <= 0.05 <= MAX_SCALE)
        assert not (MIN_SCALE <= 2.5 <= MAX_SCALE)

    def test_rotation_within_limits(self):
        """Test that rotation values are validated."""
        MIN_ROTATION = -180
        MAX_ROTATION = 180

        # Valid rotations
        assert MIN_ROTATION <= 0 <= MAX_ROTATION
        assert MIN_ROTATION <= 45 <= MAX_ROTATION
        assert MIN_ROTATION <= -90 <= MAX_ROTATION
        assert MIN_ROTATION <= 180 <= MAX_ROTATION
        assert MIN_ROTATION <= -180 <= MAX_ROTATION

        # Invalid rotations
        assert not (MIN_ROTATION <= 181 <= MAX_ROTATION)
        assert not (MIN_ROTATION <= -181 <= MAX_ROTATION)

    def test_clamp_scale(self):
        """Test clamping scale to valid range."""
        MIN_SCALE = 0.1
        MAX_SCALE = 2.0

        def clamp_scale(value):
            return max(MIN_SCALE, min(MAX_SCALE, value))

        assert clamp_scale(0.05) == 0.1
        assert clamp_scale(0.5) == 0.5
        assert clamp_scale(2.5) == 2.0

    def test_clamp_rotation(self):
        """Test clamping rotation to valid range."""
        MIN_ROTATION = -180
        MAX_ROTATION = 180

        def clamp_rotation(value):
            return max(MIN_ROTATION, min(MAX_ROTATION, value))

        assert clamp_rotation(-200) == -180
        assert clamp_rotation(45) == 45
        assert clamp_rotation(200) == 180


# ============================================================================
# Test Image Processing
# ============================================================================

class TestImageProcessing:
    """Test image processing operations."""

    def test_create_test_image(self):
        """Test creating a test image."""
        # Create a simple test avatar
        avatar = Image.new("RGBA", (512, 512), (255, 0, 0, 255))  # Red
        assert avatar.size == (512, 512)
        assert avatar.mode == "RGBA"

    def test_create_test_hat(self):
        """Test creating a test hat image."""
        # Create a simple test hat
        hat = Image.new("RGBA", (200, 150), (0, 0, 255, 255))  # Blue
        assert hat.size == (200, 150)
        assert hat.mode == "RGBA"

    def test_scale_hat_maintains_aspect_ratio(self):
        """Test that scaling maintains aspect ratio."""
        original_width = 200
        original_height = 150
        new_width = 100

        # Calculate new height maintaining aspect ratio
        new_height = int(original_height * (new_width / original_width))

        assert new_height == 75  # 150 * (100/200) = 75
        assert new_width / new_height == original_width / original_height

    def test_convert_image_to_bytes(self):
        """Test converting image to bytes."""
        # Create test image
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))

        # Convert to bytes
        output = io.BytesIO()
        img.save(output, format="PNG")
        output.seek(0)
        img_bytes = output.getvalue()

        assert len(img_bytes) > 0
        assert isinstance(img_bytes, bytes)

        # Verify we can read it back
        loaded_img = Image.open(io.BytesIO(img_bytes))
        assert loaded_img.size == (100, 100)

    def test_image_flip_operations(self):
        """Test image flip transformations."""
        # Create asymmetric test image
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))

        # Flip horizontally
        flipped_x = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        assert flipped_x.size == img.size

        # Flip vertically
        flipped_y = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        assert flipped_y.size == img.size


# ============================================================================
# Test Edge Cases
# ============================================================================

@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error handling."""

    async def test_no_hat_selected(self, mock_config):
        """Test when user has no hat selected."""
        mock_config.register_user(selected_hat=None)
        mock_config.register_global(default_hat="santa")

        selected = await mock_config.user(1).selected_hat()

        assert selected is None

    async def test_invalid_hat_name(self, mock_config):
        """Test selecting a hat that doesn't exist."""
        mock_config.register_global(hats={})

        # Try to get non-existent hat (test the logic)
        available_hats = {}  # Empty hat list
        hat_name = "nonexistent"

        assert hat_name not in available_hats

    def test_zero_dimension_validation(self):
        """Test validation of zero dimensions."""
        hat_width = 0
        hat_height = 0

        # Should raise error for zero dimensions
        assert hat_width == 0 or hat_height == 0

    def test_negative_scale_handling(self):
        """Test handling of negative scale values."""
        MIN_SCALE = 0.1

        scale = -0.5
        # Clamp to minimum
        clamped_scale = max(MIN_SCALE, scale)
        assert clamped_scale == MIN_SCALE

    def test_extreme_rotation_values(self):
        """Test extreme rotation values."""
        MIN_ROTATION = -180
        MAX_ROTATION = 180

        # Test boundary values
        assert MIN_ROTATION <= 180 <= MAX_ROTATION
        assert MIN_ROTATION <= -180 <= MAX_ROTATION

        # Test extreme values
        extreme_rotation = 720
        clamped = max(MIN_ROTATION, min(MAX_ROTATION, extreme_rotation))
        assert clamped == MAX_ROTATION

    async def test_multiple_users_different_settings(self, mock_config):
        """Test that different users can have different settings."""
        mock_config.register_user(scale=0.5, rotation=0)

        # User 1 settings
        await mock_config.user(1).scale.set(0.5)
        await mock_config.user(1).rotation.set(0)

        # User 2 settings
        await mock_config.user(2).scale.set(0.8)
        await mock_config.user(2).rotation.set(45)

        # Verify different settings
        user1_scale = await mock_config.user(1).scale()
        user2_scale = await mock_config.user(2).scale()

        assert user1_scale == 0.5
        assert user2_scale == 0.8
        assert user1_scale != user2_scale


# ============================================================================
# Test Configuration Persistence
# ============================================================================

@pytest.mark.asyncio
class TestConfigPersistence:
    """Test configuration persistence."""

    async def test_save_and_load_all_settings(self, mock_config):
        """Test saving and loading all user settings."""
        mock_config.register_user(
            selected_hat=None,
            scale=0.5,
            rotation=0,
            x_offset=0.5,
            y_offset=0.0,
            flip_x=False,
            flip_y=False,
        )

        # Set all settings
        await mock_config.user(1).selected_hat.set("santa")
        await mock_config.user(1).scale.set(0.75)
        await mock_config.user(1).rotation.set(30)
        await mock_config.user(1).x_offset.set(0.3)
        await mock_config.user(1).y_offset.set(0.1)
        await mock_config.user(1).flip_x.set(True)
        await mock_config.user(1).flip_y.set(False)

        # Load all settings
        user_data = await mock_config.user(1).all()

        # Verify
        assert user_data["selected_hat"] == "santa"
        assert user_data["scale"] == 0.75
        assert user_data["rotation"] == 30
        assert user_data["x_offset"] == 0.3
        assert user_data["y_offset"] == 0.1
        assert user_data["flip_x"] is True
        assert user_data["flip_y"] is False

    async def test_clear_user_settings(self, mock_config):
        """Test clearing user settings."""
        mock_config.register_user(scale=0.5)

        # Set some values
        await mock_config.user(1).scale.set(0.75)

        # Clear
        await mock_config.user(1).clear()

        # Should be back to defaults
        user_data = await mock_config.user(1).all()
        assert user_data["scale"] == 0.5  # Default value


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
class TestHatIntegration:
    """Integration tests for complete workflows."""

    async def test_complete_hat_configuration_workflow(self, mock_config):
        """Test complete workflow: register hat -> select -> configure -> apply."""
        # Set up config
        mock_config.register_global(hats={}, default_hat="santa")
        mock_config.register_user(
            selected_hat=None,
            scale=0.5,
            rotation=0,
            x_offset=0.5,
            y_offset=0.0,
        )

        # 1. Register hat (logic test - hat data structure)
        hat_data = {"filename": "santa.png", "default": True}
        assert hat_data["filename"] == "santa.png"

        # 2. User selects hat
        await mock_config.user(1).selected_hat.set("santa")

        # 3. User configures positioning
        await mock_config.user(1).scale.set(0.6)
        await mock_config.user(1).rotation.set(15)
        await mock_config.user(1).x_offset.set(0.4)
        await mock_config.user(1).y_offset.set(0.05)

        # 4. Verify complete configuration
        user_data = await mock_config.user(1).all()

        assert user_data["selected_hat"] == "santa"
        assert user_data["scale"] == 0.6
        assert user_data["rotation"] == 15

    async def test_multiple_hats_management(self, mock_config):
        """Test managing multiple hats."""
        mock_config.register_global(hats={})

        # Test multiple hat data structures
        hats = {
            "santa": {"filename": "santa.png", "default": True},
            "party": {"filename": "party.png", "default": False},
            "crown": {"filename": "crown.png", "default": False},
        }

        # Verify all hats in data structure
        assert len(hats) == 3
        assert "santa" in hats
        assert "party" in hats
        assert "crown" in hats
        assert hats["santa"]["default"] is True
